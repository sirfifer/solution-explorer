---
id: ug-4-viewer-identity-front-door
work_class: delegated-primary
task_class: small-feature
tier: opus
model: claude-opus-5
effort: medium
attempts_max: 2
escalate_to: frontier
branch: wt/ui-gateway-option1
scope_allow: [viewer/src/components/SystemOverview.tsx, viewer/src/components/IdentityCard.tsx, viewer/src/utils/orientation.ts, viewer/src/types.ts, viewer/src/components/__tests__/, viewer/src/utils/__tests__/, viewer/public/fixtures/]
test_paths: [viewer/tests/crawl/**, tests/**]
verify_cmd: "cd /Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway/viewer && npx tsc --noEmit && npx eslint src/ && npx vitest run 2>&1 | tail -30"
est_frontier_units: 80000
review_level: probation
---
## Objective
The Portrait posture of the overview opens on what the system is to a person: the identity statement as the headline, one chip per form factor with its evidence on click, the maintainers' README paragraph quoted as a claim, the interpreted AI summary demoted to a disclosure, the four count tiles removed from the first viewport, portrait cards that show a representative component with its description, and the posture chooser demoted to a compact secondary control. Exactly as SPEC-OPTION1-IDENTITY-FRONT-DOOR.md section 4. Done means the fixture below renders all of it in light and dark themes at 1440×900 and 390×844 with no horizontal scroll, every existing test hook still present, and the viewer still renders an orientation that lacks `identity` (older bundles) exactly as before.

## Context
Worktree `/Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway`. Viewer deps are installed (`viewer/node_modules`). Read the spec section 4 first, then `viewer/src/components/SystemOverview.tsx` in full (178 lines), `viewer/src/types.ts` around `OrientationProjection` (line 991), `viewer/src/utils/orientation.ts` (the fallback builder), and `viewer/tests/crawl/overview.spec.ts` for the hooks the crawl relies on (read only; you may not edit it). `viewer/tests/crawl/contract.ts` lists the data attributes the crawl reads.

The analyzer side (UG-2) is being written in parallel. Work against this fixture, which is the contract; add it as `viewer/public/fixtures/orientation-identity.json` (or wherever the viewer's existing test fixtures live, if there is a convention, and say which) and use it in unit tests:

```json
{
  "identity": {
    "statement": "Visual Studio Code is a desktop application for macOS, Windows and Linux, that also runs in a web browser, is driven from a terminal by a command-line tool, and is extended by plug-ins. It is written mostly in TypeScript, with Rust.",
    "statement_kind": "deterministic_composition",
    "primary": "desktop-app",
    "form_factors": [
      {"kind": "desktop-app", "label": "Desktop application", "platforms": ["macos", "windows", "linux"], "platforms_assumed": false, "how_met": "installed and opened on a computer", "component_id": "root", "evidence": [{"file": "product.json", "line": 30, "marker": "darwinBundleIdentifier"}, {"file": "package.json", "line": 188, "marker": "devDependencies.electron"}], "statement_kind": "observed_source_reference", "weight": 15204},
      {"kind": "web-app", "label": "Web application", "platforms": ["browser"], "platforms_assumed": false, "how_met": "opened in a web browser", "component_id": "src/vs/workbench", "evidence": [{"file": "src/vs/code/browser/workbench/workbench.html", "marker": "html entry"}], "statement_kind": "observed_source_reference", "weight": 4281},
      {"kind": "cli", "label": "Command-line tool", "platforms": [], "platforms_assumed": false, "how_met": "run from a terminal", "component_id": "cli", "evidence": [{"file": "cli/Cargo.toml", "line": 12, "marker": "[[bin]]"}], "statement_kind": "observed_source_reference", "weight": 87},
      {"kind": "plugin-host", "label": "Extensible by plug-ins", "platforms": [], "platforms_assumed": false, "how_met": "extended by plug-ins", "component_id": "extensions", "evidence": [{"file": "extensions/git/package.json", "marker": "contributes"}], "statement_kind": "observed_source_reference", "weight": 5145}
    ],
    "authors_claim": {"text": "This repository (\"Code - OSS\") is where we (Microsoft) develop the Visual Studio Code product together with the community. Not only do we work on code and issues here, but we also publish our roadmap, monthly iteration plans, and our endgame plans.", "source": "README.md", "line": 5, "statement_kind": "repository_claim"},
    "languages": [{"language": "typescript", "share": 0.86}, {"language": "rust", "share": 0.11}],
    "external_services": [{"name": "GitHub", "component_id": "extensions/copilot/src/extension"}],
    "truncated": false
  },
  "portrait_node_additions": {
    "share": 0.28,
    "representative": {"id": "src/vs/workbench", "name": "Workbench", "description": "Workbench: the desktop-editor UI shell and extension host bridge", "description_kind": "interpreted"}
  },
  "default_path_addition": {"reason": "broadest guided path: touches 41 components holding 63% of mapped files"}
}
```

Type additions (`viewer/src/types.ts`): `OrientationProjection.identity?: OrientationIdentity | null`, `OrientationNode.share?: number`, `OrientationNode.representative?: {...}`, `default_path.reason?: string`. All optional so old sidecars type-check.

Fallback (`buildOrientationFallback`): emit `identity: null`; do not attempt to derive identity in the browser.

Layout per spec section 4. Provenance marks: reuse the wording the deployment posture panel already uses ("Observed source reference" / "Repository claim") so the page has one vocabulary. The evidence popover can be a `<details>`/`<dialog>` or a small absolutely-positioned panel; it must be keyboard reachable and close on Escape. Chip click with a non-root `component_id` also offers "Open in workbench" via the existing `openComponent`.

Counts: remove the four `Scale` tiles from `Portrait`; add the one-line summary with a button that calls `onTrust`. Keep `Scale` in `Questions`.

Posture chooser: same three buttons and attributes, rendered smaller and right-aligned in the header row of the main area with the label "Other ways in"; the "Choose the opening posture" eyebrow and its sentence go away.

Styling follows the file's existing Tailwind idiom and dark-mode pattern (`darkMode ? ... : ...`). Do not introduce a new styling approach.

Manual check (report with screenshots saved under `viewer/.ug4-screens/`, which is gitignored if there is a pattern for it, else list the paths and the orchestrator will delete them): run `npx vite --port 5179` against a served bundle if one exists at `../.testboard/serve/vscode` (it may not carry identity yet; then use the fixture through a vitest render, and screenshots come from the orchestrator at integration). Do not spend more than two iterations on visual polish; the orchestrator reviews the live page.

## Acceptance
- With the fixture: H2 carries `data-testid="identity-statement"` and the exact statement; four chips with `data-testid="form-factor"` and `data-kind`; clicking the desktop-app chip reveals two evidence rows reading `product.json:30 darwinBundleIdentifier` and `package.json:188 devDependencies.electron`; the blockquote with `data-testid="authors-claim"` shows the claim and a caption naming README.md and "Repository claim"; the interpreted statement is inside a `<details>` whose summary reads "Interpreted summary"; no element with `data-se="stat"` renders in the Portrait posture; the one-line summary shows the three counts and opens the trust drawer.
- Without `identity` (fixture stripped): the headline logic and layout are exactly today's, with the count line replacing the tiles (that change applies regardless). A unit test renders both.
- Portrait cards show `representative.name`, description clamped to two lines, `member_count` and share as a percentage, and an "interpreted" mark when `description_kind` is interpreted; cards without `representative` render as today.
- Posture chooser keeps `data-testid="overview-direction"`, `data-direction`, `data-selected` and the values `portrait`, `questions`, `atlas`. All other hooks listed in spec section 4 remain.
- `npx tsc --noEmit` and `npx eslint src/` clean. `npx vitest run`: capture the set of failing test files before your change and after; the after set must be a subset of the before set (the 86 localStorage failures are environment noise; do not chase them, do not let a new one hide among them). Paste both lists in the report.
- Reduced motion respected (no new animation without the `motion-safe:` guard the file already uses, if any; otherwise none).
- Report: files changed, the two failing-file lists, screenshots or the reason they could not be taken, and any spec ambiguity with the choice made.

## Out of scope
- No edits under `viewer/tests/crawl/` (UG-6 owns it) or `analyzer/`.
- No changes to Questions or Atlas postures beyond what the shared components force.
- No new dependencies. No routing or store changes except reading the new fields.
- Commit when the verify command is green, on `wt/ui-gateway-option1`, message starting with the task id. Never push.

## House conventions
- No em dashes or en dashes anywhere, including UI copy and comments.
- UI copy is plain language for a non-developer: "Desktop application", "Web application", "Command-line tool", "Extensible by plug-ins", "installed and opened on a computer". Never expose kind ids like `plugin-host` to the reader.
- Comments explain why, briefly, in the voice of the file (see the comment in `openComponent`).
- Run the verify command before reporting.
