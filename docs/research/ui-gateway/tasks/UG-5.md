---
id: ug-5-readme-hero-image
work_class: delegated-primary
task_class: small-feature
tier: sonnet
model: claude-sonnet-5
effort: medium
attempts_max: 2
escalate_to: opus
branch: wt/ui-gateway-option1
scope_allow: [analyzer/derive/identity.py, analyzer/project/pipeline.py, scripts/assemble-serve.py, viewer/src/components/IdentityCard.tsx, viewer/src/types.ts, tests/test_identity.py, viewer/src/components/__tests__/]
test_paths: [viewer/tests/crawl/**, tests/test_human_views.py]
verify_cmd: "cd /Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway && .venv-wt/bin/python -m pytest tests/test_identity.py -q && .venv-wt/bin/python -m ruff check analyzer/ scripts/ tests/ && cd viewer && npx tsc --noEmit && npx eslint src/"
est_frontier_units: 25000
review_level: standard
---
## Objective
Status: OPTIONAL this week; dispatched only after UG-7 integration is green. The B1 tier of SHOW-ME-THE-APP.md: when the root README carries an image, show it on the front door stamped with its source. An image whose path is inside the repository is copied into the bundle and rendered; an image at a remote URL is never fetched or hot-linked and is shown as a link with its alt text, because the bundle must not load third-party resources.

## Context
Read SHOW-ME-THE-APP.md section 4 (Layer B, tier B1) and the spec section 2.2 for where README text is available. UG-1 and UG-2 have landed: `arch["identity"]` exists and reaches `manifest.json`; the viewer renders `identity` via `IdentityCard.tsx` (UG-4).

Derive: in `analyzer/derive/identity.py`, extract the first README image: Markdown `![alt](path)` or HTML `<img src="..." alt="...">`, skipping badge images (paths containing `shields.io`, `badge`, or `.svg` under 2 KB). Record `identity.readme_image = {"src", "alt", "line", "in_repo": bool, "statement_kind": "repository_claim"}`. `in_repo` is true when the path resolves to a file in the store.

Bundle: for in-repo images, `assemble-serve.py` (or the projection step, whichever already copies upstream files like `UPSTREAM-LICENSE.txt` into the bundle; follow that precedent) copies the file to `architecture/assets/readme-image.<ext>` and rewrites `src` to that path. Cap at 2 MB; larger images are recorded but not copied (`copied: false`).

Viewer: in `IdentityCard.tsx`, below the maintainers' quote: the image (max height 320 px, object-fit contain) with caption "From README.md at commit {short}, repository claim". For remote images: a link with the alt text and the caption "Image hosted outside the repository; not loaded". Never emit an `<img>` with a remote `src`.

## Acceptance
- Tests: Markdown and HTML forms both extract; badges are skipped; a remote URL yields `in_repo: false`; an in-repo path yields `in_repo: true` and the copy step produces the asset with the rewritten path.
- VS Code's README (its image is a remote GitHub user-attachments URL) renders as a link, not an image.
- No network access anywhere in the pipeline or the viewer for this feature.
- Verify command clean; report files changed and output tail.

## Out of scope
- No image processing, resizing or format conversion.
- No changes to the crawl contract.
- Commit when the verify command is green, on `wt/ui-gateway-option1`, message starting with the task id. Never push.

## House conventions
- No em dashes or en dashes anywhere.
- Follow the existing bundle-asset precedent rather than inventing a new copy step.
- Run the verify command before reporting. Use `.venv-wt/bin/python`.
