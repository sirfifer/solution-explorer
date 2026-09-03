---
id: ug-7-integration
work_class: delegated-primary
task_class: harness-build
tier: opus
model: claude-opus-5
effort: medium
attempts_max: 2
escalate_to: frontier
branch: wt/ui-gateway-option1
scope_allow: [tests/golden/**, docs/testing/RUN-2026-09-0*-ui-gateway.md, .testboard/**, demos/review-corrections/**]
test_paths: []
verify_cmd: "cd /Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway && .venv-wt/bin/python -m pytest tests/ -q 2>&1 | tail -3 && .venv-wt/bin/python scripts/golden-corpus.py check flask && .venv-wt/bin/python scripts/golden-corpus.py check fastapi"
est_frontier_units: 60000
review_level: probation
---
## Objective
Prove option 1 on the two canonical subjects, end to end: reproject VS Code and UnaMentis iOS from copies of their stores, serve both bundles, run the crawl with this worktree's harness, capture the overview at desktop and mobile in both themes, refresh the golden baselines deliberately, and write the run record. Done means the acceptance list in SPEC-OPTION1-IDENTITY-FRONT-DOOR.md section 7 is checked item by item with evidence, and anything that fails is listed with its bucket (viewer, sidecar, reprojection, or spec).

## Context
Runs after UG-1, UG-2, UG-4 and UG-6 are committed. Read the spec section 6 and 7, `docs/testing/RUN-2026-09-02-vscode-demo-gate.md` (the previous run record and its command block, which this task mirrors), and `/Volumes/Studio/dev/solution-explorer/.testboard/live/ACTIVE-DATASETS.md` (canonical store and projection paths; the stores are the only copies of about $236 of enrichment: never open them in place, copy first).

Steps:
1. Copy the stores: `cp` the VS Code `index.db` (plus `-wal` and `-shm` if present) and the UnaMentis `index.db` into `.testboard/stores/<subject>/` in this worktree.
2. Reproject, venv interpreter only:
   `.venv-wt/bin/python analyze.py /Volumes/Studio/dev/.demo-corpus/vscode --engine v2 --store .testboard/stores/vscode/index.db --output .testboard/derived/vscode/architecture --split`
   `.venv-wt/bin/python analyze.py /Volumes/Studio/dev/unamentis-ios --engine v2 --store .testboard/stores/unamentis-ios/index.db --output .testboard/derived/unamentis-ios/architecture --split`
   Confirm the symbol and relationship counts match the previous run record (VS Code about 151k symbols, 5,45x relationships; a zero means the wrong interpreter). Confirm `manifest.json` carries `identity` and `orientation.json` carries the statement.
3. `scripts/reorient.py --check` on both projections must exit 0 (the projection and the script agree).
4. Serve: `python3 scripts/assemble-serve.py vscode --projection .testboard/derived/vscode/architecture --corrections demos/review-corrections/vscode.json` then `python3 -m http.server 5185 --bind 127.0.0.1 --directory .testboard/serve/vscode`; same for `unamentis-ios` on 5186 with its corrections file. Use ports 5185 and 5186 so the owner's running demos on 5175 and 5176 are untouched.
5. Crawl both from `viewer/`: `CRAWL_BASE_URL=http://127.0.0.1:5185 CRAWL_PROFILE=quick npx playwright test -c tests/crawl/playwright.config.ts`, then `python3 scripts/crawl-report.py .testboard/runs/<run id>`. Repeat for 5186. UnaMentis must hold 56/56 plus O9 (note or pass) and O10; VS Code must pass O1 to O10.
6. Screenshots: Portrait posture at 1440×900 and 390×844, light and dark, for both subjects, saved under `docs/testing/ui-gateway-screens/` as `<subject>-<size>-<theme>.png`.
7. Golden corpus: run the two checks, read the diff, confirm every changed line is the `identity` addition or the portrait fields, then refresh the baselines with the corpus script's update mode and re-run the checks to green. Any other change in the diff is a regression: stop and report it instead of refreshing.
8. Full `pytest tests/ -q` (expect the one known worktree-only failure, `test_pruned_directory_row_stands_in_for_its_contents`, and nothing else), `ruff`, viewer `tsc`, `eslint`, `vitest` (failing-file set diffed against the pre-change set recorded by UG-4).
9. Write `docs/testing/RUN-2026-09-0X-ui-gateway.md` in the shape of the 2026-09-02 record: what changed, the four-bucket split of anything wrong, the commands, the crawl numbers, the screenshots, cumulative token spend across UG-1 to UG-7 as reported by each task, and the spec section 7 acceptance list with a verdict per line.
10. Commit the run record, screenshots and golden refresh on the branch. Never push. Stop the http servers.

## Acceptance
- Spec section 7, every line, with evidence (a screenshot path, a crawl rule id, or a JSON excerpt) and a verdict.
- The VS Code statement on the served page is character-for-character the one in spec 2.4 up to the external-services sentence; if it differs, the difference is explained by a detector's evidence, not by a template bug.
- The UnaMentis portrait before and after is compared (member counts per group) and the change is explained.
- Golden refresh contains only the intended additions.
- The run record is honest about anything not verified.

## Out of scope
- Publishing, deploying, pushing, or touching the live demos on 5175 and 5176.
- Fixing defects found in step 5 beyond one-line viewer fixes that a rule points at directly; larger defects go into the run record's bucket table for the frontier review.
- Options 2, 3, 4 of SHOW-ME-THE-APP.md.

## House conventions
- No em dashes or en dashes anywhere, including the run record.
- Venv interpreter for every analyzer command. Copies of stores, never the originals.
- The run record follows the 2026-09-02 record's structure and voice.
- Commit when green, message starting with `UG-7`. Never push.
