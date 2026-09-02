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

The committed `baseline.json` embeds the absolute `root_path` of the machine
that generated it (a local cache path). That field is environment-specific and
is intentionally NOT one of the diffed sections, so a check regenerating under a
different `root_path` (CI on Linux, or a re-baseline on macOS) never reports it
as drift.

## Corpora

- **flask** (`pallets/flask`, BSD-3-Clause, pinned at 3.1.3). The first corpus.
  Chosen for the regression role: stable, small, permissively licensed, and a
  SWE-bench standard repo (external comparability), which keeps diff noise low
  while the harness is shaken out.
- **fastapi** (`tiangolo/fastapi`, MIT, pinned at 0.139.2). The second corpus,
  added for lens breadth: the richest single-repo surface for this tool
  (routing, Depends DI, Pydantic data entities, OpenAPI capabilities). Pinned
  post the 0.137.0 (June 2026) router-internals refactor so the baseline sits on
  the settled router tree. Its `corpus.lock` excludes the twelve translated docs
  directories (docs/en, the canonical English docs, stays scanned) and
  `docs_src/` (345 of its 461 Python files are `_an`/`_py39`/`_py310`
  version-variant near-duplicates of the same tutorial snippets, pure
  duplication noise; the `fastapi/` package and `tests/` already exercise the
  full lens surface). The baseline is about 6.6 MB, committed by design.

`large-repository-validation` stays a separate scale proof, not a daily-diff corpus.

## Using the harness

```
python3 scripts/golden-corpus.py list             # configured corpora + baseline state
python3 scripts/golden-corpus.py check flask       # fetch, analyze, diff vs baseline (exit 1 on drift)
python3 scripts/golden-corpus.py generate flask -o /tmp/flask.json   # just produce a projection
python3 scripts/golden-corpus.py baseline flask    # re-baseline (see below)
python3 scripts/golden-corpus.py parity flask      # full-vs-incremental parity at scale (G4)
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

`check` runs the G1 projection diff, which compares twelve structural sections
(components, relationships, findings, coverage, inventory, data_entities,
entity_access, capabilities, concerns, enrichment, stats, and supply_chain). The
`stats` roll-ups (total_components/files/lines/symbols/relationships,
total_size_bytes, and per-language line counts) and the `supply_chain` count
roll-ups (dependencies overall, per ecosystem, and per count bucket including
warnings and pin status) were added specifically to catch the gross extraction
and SBOM regressions the identity-keyed sections miss: a symbol-extraction pass
that silently halves its output now moves `stats.total_symbols`, and a broken
SBOM pass moves the `supply_chain` counts. `concerns` are compared by id
(added, removed).

What the check still does NOT catch: the `symbols` array is compared only at the
`stats` count level, not per-symbol identity, so a change that swaps one symbol
for another while keeping the total constant would not register. `concerns` are
compared by id, not by their internal membership. Treat a clean `check` as "the
structural representation and the roll-up counts did not change," not as "nothing
regressed."

## Full-vs-incremental parity at scale (G4)

`parity <corpus>` proves the incremental-equals-full contract from
`docs/remediation/ROBUSTNESS-STRATEGY.md` on real code at scale: a warm
incremental run must produce the same projection as a cold full regeneration, so
a daily full regeneration is provably unnecessary. It runs two checks, both
required to pass:

1. NO-CHANGE parity: a cold full generation (the store is wiped first) and a warm
   rerun (the store is reused) over the unchanged tree must match.
2. CHANGED-FILE parity: one source file is edited, a warm incremental run and a
   cold full run are taken over the mutated tree, and they must match. This
   proves the changed-file path, not only the no-change path. The edit is always
   reverted (a `finally`), so the frozen corpus is left untouched.

The comparison standard is stronger than the `check` semantic diff: it strips the
same volatile fields the engine-parity fixture guard strips (the single allowlist
lives in `analyzer/parity.py`, reused by both) and then compares the projections
BYTE-for-byte with list order preserved, so it also catches an ordering
regression a by-id diff would miss. A mismatch is a real incremental-vs-full
engine divergence, never a harness bug: the command prints the G1 diff as the
human explanation and exits 1. It is never weakened to make a real difference
pass.

Both corpora pass today (flask and fastapi, no-change and changed-file variants).

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
   change they record, and add an entry under "Baseline history" below. An
   engine change that moves the diffed counts carries its re-baseline in the
   same PR: that is the only moment the author can state the intent next to
   the diff, and `main` stays green.

To advance the frozen target itself (adopt a newer upstream release), update the
`ref` and `commit` in `corpus.lock` to the new pinned SHA, then re-baseline.

## Baseline history

Each entry records an approved re-baseline: what engine change moved the
numbers, and why that change was intended. A baseline is only ever regenerated
by `scripts/golden-corpus.py baseline <name>` under the frozen toolchain, never
edited by hand; a repository-wide text sweep must exclude these files.

- **2026-09-02, both corpora.** CI workflow files (`.github/workflows/*.yml`)
  are now first-class repository files: kept in the architecture, assigned to
  the nearest component (the repository root here), and counted in statistics,
  search and coverage. Before, the deriver skipped rows cached as `ci_config`,
  so those files were credited to coverage but owned by nothing and invisible
  to every viewer surface (UnaMentis comprehension review finding O8, fixed in
  6e32b50). Effect on the frozen targets: fastapi gains its 24 workflow files
  (+1,676 config lines), flask its 4 (+165); root's activity aggregates grow
  with the files it now owns. Two smaller movements ride along from the same
  range: extract tier p5-extract/10 routes Markdown away from the rule
  extractor, so one fastapi rule sourced from `docs/en/docs/release-notes.md`
  is gone, and four fastapi test rules changed id only because their summary
  whitespace was normalized. The regeneration also restores a real path the
  repository-wide product-rename sweep had rewritten inside the committed
  fastapi baseline (`docs/en/docs/img/vscode-completion.png`), which is why
  baselines must never be edited by hand. The engine change is confirmed
  intended by the owner; the decision record is
  `docs/testing/GOLDEN-DRIFT-2026-09-02.md`. Toolchain pins unchanged.

## CI

`.github/workflows/golden-corpus.yml` runs `check` on every configured corpus
(flask and fastapi, as a matrix with `fail-fast: false` so each is an
independent regression signal) on pull requests that touch the engine (analyzer,
`analyze.py`, or the harness/diff scripts) and fails on drift. The default
`pytest` suite stays hermetic (no clone); the live fetch+generate+check is the
workflow, plus opt-in tests guarded by `GOLDEN_CORPUS_NETWORK=1`.

The same workflow has a `parity` job (both corpora) that runs `parity` (G4). It
is `workflow_dispatch` only, not on every PR: it runs four analyses per corpus
(about four times the `check` cost), and the incremental-equals-full contract it
proves changes only with the incremental engine, not with most PRs, so running
it on demand keeps PR CI fast while the per-PR `check` still catches projection
regressions. Trigger it from the Actions tab when the incremental or extraction
path changes. The opt-in `test_live_parity_holds` (guarded by
`GOLDEN_CORPUS_NETWORK=1`) exercises the same path locally.
