# Golden corpus drift on main, 2026-09-02: what it is and how to reconcile it

Written for the session that owns the front-door and engine work, so the two
sessions can agree on one disposition. Everything below was read from the
repository and the CI logs; nothing is inferred from memory.

## The symptom

`golden-corpus.yml` fails on `main` since e89cd55 (the Overview merge). Both
corpora report drift in the `stats` section only:

| Corpus | total_files | languages.yaml | lines_by_class.config | total_lines |
|---|---|---|---|---|
| fastapi | 788 to 812 (+24) | 5476 to 7152 (+1676) | 1027 to 2703 (+1676) | +1676 |
| flask | 115 to 119 (+4) | 36 to 201 (+165) | 417 to 582 (+165) | +165 |

The other eleven diffed sections (components, relationships, findings,
coverage, inventory, data entities, entity access, capabilities, concerns,
enrichment, supply chain) report no change. The last green run on `main` was
12480f1 on 2026-08-28. The golden script and workflow themselves did not
change in the range.

## The cause, to the line

The added files are the corpora's GitHub Actions workflows. At the pinned
commits, `tiangolo/fastapi` has exactly 24 files under `.github/workflows` and
`pallets/flask` has exactly 4, matching the drift file for file. They count as
`yaml` and as `config` lines because the analyzer now keeps them in the
architecture.

The change is in `analyzer/derive/components.py`, `associate_files`, commit
6e32b50 "Remediate UnaMentis front-door trust findings", carried to `main` by
01133d2. Before:

```python
if frow.get("parse_status") == "ci_config":
    # Store-internal rows cached for the root-bounded CI check; the
    # old engine excludes these paths from the architecture's files.
    continue
```

After, the skip is removed with this comment:

```python
# Root-bounded CI files are intentionally cached without a language
# parser, but they are still real repository files. Keep them in the
# architecture and assign them to the nearest component (normally the
# repository root) so ownership and search never silently lose them.
```

## Why it was done

It answers a verified finding from the UnaMentis comprehension review, O8 in
`docs/quality/runs/unamentis-ios/2026-09-01/ORCHESTRATOR-FINDINGS.md`:
`stats.total_files` said 751 while `coverage.parsed` said 757, and the six
missing files were exactly the subject's `.github/workflows/*.yml`. They were
parsed and credited to coverage but owned by no component, absent from search
and from every UI surface. The recheck record marks O8 fixed: the six files
are owned by `root` and the file count agrees across stats, search and
coverage.

So the engine change is deliberate, motivated by a real inconsistency, and it
makes the accounting file-complete. The golden drift is the expected
consequence of that decision, not a regression in the analyzer. The gate is
doing exactly what it exists to do: forcing the change to be acknowledged
against a frozen subject.

## Assessment

**Agree with the change.** Counting a file for coverage while no component
owns it was the inconsistency; either both or neither is defensible, and both
is the honest choice for a tool whose promise is that every artifact is
accounted for. The alternative, a visible `excluded:ci` disposition kept out
of the totals, would have kept the old baselines but reintroduced a class of
file the UI cannot reach.

**Three things to reconcile, in order of weight.**

1. **The re-baseline did not ship with the engine change.** The golden
   corpus README states the contract: a stats change from our engine is
   either an intended improvement, re-baselined and committed, or a
   regression to investigate. The change landed without either, and `main`
   has been red on this workflow since. The fix is mechanical (below); the
   process point is that an engine change that alters counts carries its
   re-baseline in the same PR, because that is the only moment the author
   can state the intent alongside the diff.

2. **The committed baselines were edited by hand.** In the same range both
   `tests/golden/*/baseline.json` changed by one string inside the
   `coverage` section: the inventory label "Solution Explorer state" became
   "SysCorpus state". That came from the repository-wide product rename,
   which also rewrote comments in the crawl suite ("VS Code" became "private
   large-repository validation corpus" in sentences where it no longer reads
   naturally). The README says a baseline is "a real, unmodified analyze.py
   output". The effect here is harmless, since the engine's label changed
   the same way, but the baselines are no longer a real generation, and a
   rename sweep that edits data fixtures and code comments blindly is worth
   a rule: fixtures and quoted output are excluded from such sweeps, or are
   regenerated afterwards.

3. **The projection diff did not notice the ownership change.** Twenty-four
   files moved from unowned to owned by `root` on fastapi, and the
   `components` section reported no difference; only `stats` did. Either the
   components comparator does not look at per-component file lists, or root
   is special-cased. Either way, a change in which component owns which
   files is precisely the kind of drift the G1 diff should surface, and it
   was caught only through the roll-ups added for gross extraction changes.
   Worth a look at `scripts/projection-diff.py`.

Two smaller observations. The extract tier moved from p5-extract/8 to /10 in
the same range (queue-name and websocket signal rules, JSON and Markdown
routed away from the rule extractor); on these two Python corpora it changed
nothing the diff can see, which is reassuring, but a warm store elsewhere will
re-extract once. And workflow YAML now appears in root's Files tab and in
search results for every subject, which is the intended user-visible side of
the same decision and should be stated somewhere a reader of the viewer's
counts can find it.

## What the regeneration actually changed (reviewed before approval)

Compared field by field against the previously committed baselines:

- fastapi and flask: root gains its 24 and 4 workflow files; `stats` moves as
  the CI report said; root's activity aggregates (commits, churn, lines) grow
  with the files it now owns.
- fastapi rules 44 to 43: one `validation` rule sourced from
  `docs/en/docs/release-notes.md` is gone, because extract tier
  p5-extract/10 routes Markdown away from the rule extractor (the same range,
  intended). Four `calculation` rules in `tests/` changed id only: their
  summary text lost a doubled space. flask rules unchanged.
- fastapi coverage rows: one path corrected. The old baseline carried
  `docs/en/docs/img/reference-repository-completion.png`; the file in the
  repository is `vscode-completion.png`. The product-rename sweep had
  rewritten a subject's real path inside an approved baseline. This is
  concern 2 above, made concrete.
- New top-level sections `orientation`, `support`, `security` now ride in the
  artifact (98a68b3); `generated_at` and `root_path` differ as always. None of
  these is a diffed section.

Toolchain: regenerated in a fresh venv installed with
`-c tests/golden/constraints.txt`; the frozen pins were already exactly what
that environment resolved, so `constraints.txt` is unchanged.

## Disposition taken (2026-09-02)

Owner confirmed the intent: CI workflow files are first-class repository files,
assigned to the nearest component and included in statistics, search and
coverage. Both baselines regenerated on current `main`, both checks pass, a
dated entry added under "Baseline history" in `tests/golden/README.md`, and the
same-PR rule written into the re-baseline procedure. 6e32b50 is not reverted.
The components-comparator blind spot stays a separate follow-up.

## Recommended disposition (as written before the decision)

1. Confirm the intent with the engine-change owner: CI workflow files are
   repository files, owned by the nearest component, counted in stats,
   search and coverage. This note assumes yes.
2. Re-baseline both corpora on `main`, from a clean checkout at the current
   head, installing with `-c tests/golden/constraints.txt` as the README
   requires, so the committed baselines are again unmodified generations:

   ```bash
   python3 scripts/golden-corpus.py baseline flask
   python3 scripts/golden-corpus.py baseline fastapi
   python3 scripts/golden-corpus.py check flask && python3 scripts/golden-corpus.py check fastapi
   ```

   Commit the two baselines alone, with a message that cites O8 and the
   file-complete accounting decision, so the next reader of `git log` on
   those files sees why the counts moved.
3. Add two sentences to `tests/golden/README.md` under a dated "Baseline
   history" heading: what changed on 2026-09-02 and why, and the rule that
   engine changes altering counts carry their re-baseline in the same PR.
4. Separately, look at why the components comparator was silent on the
   ownership change.

Nothing here blocks the viewer work that merged today; the two PRs from this
session touched no analyzer code, and the golden workflow does not run on
their paths.
