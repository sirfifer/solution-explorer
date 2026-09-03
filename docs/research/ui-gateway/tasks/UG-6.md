---
id: ug-6-reorient-and-crawl-contract
work_class: delegated-primary
task_class: small-feature
tier: sonnet
model: claude-sonnet-5
effort: medium
attempts_max: 2
escalate_to: opus
branch: wt/ui-gateway-option1
scope_allow: [scripts/reorient.py, tests/test_reorient.py, viewer/tests/crawl/overview.spec.ts, viewer/tests/crawl/contract.ts, viewer/tests/crawl/README.md]
test_paths: [tests/test_human_views.py, tests/test_identity.py, viewer/src/**]
verify_cmd: "cd /Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway && .venv-wt/bin/python -m pytest tests/test_reorient.py -q && .venv-wt/bin/python -m ruff check scripts/reorient.py tests/test_reorient.py && cd viewer && npx tsc --noEmit -p tests/crawl/tsconfig.json 2>/dev/null || npx tsc --noEmit"
est_frontier_units: 30000
review_level: standard
---
## Objective
Two well-fenced deliverables. First, `scripts/reorient.py`, which regenerates `orientation.json` for an existing projection directory without re-parsing, per SPEC-OPTION1-IDENTITY-FRONT-DOOR.md section 5. Second, two new crawl rules in `viewer/tests/crawl/overview.spec.ts`, O9 and O10, that assert the identity front door once it exists, with rule ids registered in `contract.ts` and documented in the crawl README.

## Context
Worktree `/Volumes/Studio/dev/.worktrees/solution-explorer--ui-gateway`, venv `.venv-wt/bin/python`, viewer deps installed. Read the spec sections 4 (for the test hooks) and 5. Then `analyzer/project/human_views.py` `build_orientation(arch, *, coverage, support, security)` and `write_human_view`, `scripts/assemble-serve.py` (house style for a script over a projection directory, argparse layout, how it loads `manifest.json`), and `viewer/tests/crawl/overview.spec.ts` plus `contract.ts` (how rules O1 to O8 are written, tagged and registered).

Script behaviour:
- `reorient.py <projection-dir> [--check]`. Loads `manifest.json` (required), `coverage.json`, `support.json`, `security.json` (optional, pass None when absent). Calls `build_orientation`. Default: writes `orientation.json` in place with the same indentation `write_human_view` uses. `--check`: prints a unified diff between the existing file and the regenerated document; exit 0 when identical, 1 when different.
- Exit 2 with a one-line warning on stderr when `manifest.json` has no top-level `identity` key ("projection predates the identity pass; reproject with analyze.py"). Still regenerate when not `--check`? No: exit 2 and write nothing; this projection needs a real reprojection.
- Deterministic; no network; no model.
- Tests in `tests/test_reorient.py`: a tmp projection with a minimal manifest that includes `identity: null` regenerates cleanly; one without `identity` exits 2; `--check` returns 1 on a stale file and 0 after regeneration. Build the manifest from the `_architecture()` idiom in `tests/test_human_views.py` (import it if it is importable; otherwise copy the minimal shape, not the whole helper).

Crawl rules (Playwright, house style of O1 to O8):
- O9 "the front door says what the system is, with evidence": on `?mode=overview`, if the sidecar (`architecture/orientation.json`, fetched the way the other rules read the sidecar) has non-null `identity.statement`, then `[data-testid="identity-statement"]` renders that exact text, `[data-testid="form-factor"]` count equals `identity.form_factors.length`, and clicking the first chip reveals text containing that record's first evidence `file`. If the sidecar's `identity` is null, the rule passes with a recorded note "identity absent in sidecar" (the honest-empty pattern the spec file already uses). Tags desktop and mobile.
- O10 "counts stay out of the first viewport": on the Portrait posture, no `[data-se="stat"]` is inside the viewport at load, at both desktop and mobile sizes; the trust chip or count line is present. Tags desktop and mobile.
- Register both ids wherever O1 to O8 are registered (`contract.ts`), and add two lines to the crawl README table.
- Do not run the full crawl against the currently served bundle as a gate; it predates the identity pass and O9 will record the absent note. Do run `npx playwright test -c tests/crawl/playwright.config.ts --list` to prove the spec compiles and both rules are discovered, and paste that output.

## Acceptance
- `tests/test_reorient.py` passes; ruff clean; the script's `--help` reads sensibly.
- `--list` output shows O9 and O10 with the expected tags.
- The two rules follow the existing rule shape exactly (same helpers for reading the sidecar, same tagging, same evidence capture idiom); no new helper unless the existing ones cannot express it, and then say why.
- No edits outside `scope_allow`. No edits to `viewer/src/**`.
- Report: files changed, verify output tail, the `--list` output, and any spec ambiguity with the choice made.

## Out of scope
- Do not change O1 to O8.
- Do not touch `analyzer/**` or `viewer/src/**`.
- Commit when the verify command is green, on `wt/ui-gateway-option1`, message starting with the task id. Never push.

## House conventions
- No em dashes or en dashes anywhere.
- Scripts: argparse, a `main()` returning an int, `if __name__ == "__main__": raise SystemExit(main())`, docstring at top saying why the script exists (match `assemble-serve.py`).
- Tests are pytest functions with descriptive names.
- Run the verify command before reporting. Use `.venv-wt/bin/python`.
