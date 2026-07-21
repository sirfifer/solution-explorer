# Golden corpus (regression harness)

This directory holds the golden-master regression corpus described in
`docs/remediation/REGRESSION-STRATEGY.md` (card G2). It is the clean regression
signal that the always-changing demo and dogfood cannot give: a respected
real-world repository held FROZEN at a pinned commit, so any diff between a fresh
generation and the approved baseline is attributable to OUR engine change, not
to the target moving.

## Storage model

Fetch-at-pinned-commit plus a committed baseline (owner decision, 2026-07-20).
The corpus source is never vendored into this repo.

- `<name>/corpus.lock` (committed): pins the exact repo and commit SHA, plus any
  scan excludes. A pin is a full 40-char SHA, not a mutable tag.
- `<name>/baseline.json` (committed): the approved full projection. This is the
  golden master. It is a real, unmodified `analyze.py` output.
- `.golden-cache/<name>/` (gitignored): the source fetched on demand at the
  pinned commit. A depth-1 fetch of the exact SHA, so no history is downloaded.

## Corpora

- **flask** (`pallets/flask`, BSD-3-Clause, pinned at 3.1.3). The first corpus.
  Chosen for the regression role: stable, small, permissively licensed, and a
  SWE-bench standard repo (external comparability), which keeps diff noise low
  while the harness is shaken out.
- **fastapi** (planned second): richest single-repo lens surface (routing,
  Depends DI, Pydantic entities, OpenAPI), pinned post the 0.137.0 router
  refactor with translated docs excluded.

`vscode` stays a separate scale proof, not a daily-diff corpus.

## Using the harness

```
python3 scripts/golden-corpus.py list             # configured corpora + baseline state
python3 scripts/golden-corpus.py check flask       # fetch, analyze, diff vs baseline (exit 1 on drift)
python3 scripts/golden-corpus.py generate flask -o /tmp/flask.json   # just produce a projection
python3 scripts/golden-corpus.py baseline flask    # re-baseline (see below)
```

`check` is the gate: a non-empty diff that is not an intended improvement is a
regression to investigate before merge. The diff is the G1 projection-diff tool,
so the harness and the demo/dogfood two-slot flow (G3) speak the same delta
language.

## Frozen toolchain

The corpus freezes the target; `constraints.txt` freezes the analyzer's parsing
toolchain (tree-sitter grammars and the rules loader) that produced the baseline,
so a fresh generation resolves the same versions rather than whatever the
project's `>=0.23` ranges pick at run time. The golden-corpus workflow installs
with `-c tests/golden/constraints.txt`, and so should you when re-baselining.
The project's general dependency ranges in `pyproject.toml` stay ranges for
Dependabot; the pin lives only here.

## What the check does and does not catch

`check` runs the G1 projection diff, which compares the nine structural sections
(components, relationships, findings, coverage, inventory, data_entities,
entity_access, capabilities, enrichment). It intentionally does NOT diff
`symbols`, the `supply_chain` SBOM, `concerns`, or `stats`, so a regression
confined to those (for example a symbol-extraction pass that silently halves its
output, or a broken SBOM) would pass `check` with no drift. Extending the diff to
cover `stats` roll-ups and `supply_chain` counts is tracked as a follow-up in
`docs/remediation/TASKS.md` (Discovered table, 2026-07-20). Treat a clean `check`
as "the structural representation did not change," not as "nothing regressed."

## Re-baseline procedure

Re-baseline at a stopping point on purpose, never to silence a diff you have not
understood:

1. Run `python3 scripts/golden-corpus.py check flask` and read the drift.
2. Confirm every change is an intended engine improvement (not a regression).
3. Reinstall the frozen toolchain (`pip install -e ".[all,dev]" -c
   tests/golden/constraints.txt`), then run `python3 scripts/golden-corpus.py
   baseline flask` to regenerate and approve the new `baseline.json`.
4. Regenerate `constraints.txt` from the same environment so the pins and the
   baseline stay in lock step (`pip freeze | grep -iE '^tree.sitter|^PyYAML' |
   sort`).
5. Commit the new baseline and constraints with a message stating what engine
   change they record.

To advance the frozen target itself (adopt a newer upstream release), update the
`ref` and `commit` in `corpus.lock` to the new pinned SHA, then re-baseline.

## CI

`.github/workflows/golden-corpus.yml` runs `check flask` on pull requests that
touch the engine (analyzer, `analyze.py`, or the harness/diff scripts) and fails
on drift. The default `pytest` suite stays hermetic (no clone); the live
fetch+generate+check is the workflow, plus an opt-in test guarded by
`GOLDEN_CORPUS_NETWORK=1`.
