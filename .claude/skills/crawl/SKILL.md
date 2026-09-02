---
name: crawl
description: Run the adaptive GUI crawl against a subject (local or remote) and read the result. Design authority is docs/testing/GUI-CRAWL-DESIGN.md.
---

# /crawl - the adaptive GUI crawl

A subject-agnostic Playwright suite that discovers what the viewer's data
warrants (entry points, lenses, tours) and what the DOM actually shows, then
pursues every present feature to a stated depth: opened, used, stepped
through, closed, and reset. Design authority is
`docs/testing/GUI-CRAWL-DESIGN.md`; the operator's manual with the full
selector table is `viewer/tests/crawl/README.md`.

## When to run it

1. **After any significant change to the viewer, the store, the lenses, or
   the projection schema.** `quick` against the current canonical subject,
   before the work is called done. A PR that changes viewer behaviour
   reports the run id.
2. **After every new subject's full pass.** Once after `assemble` (analyze
   plus assemble), again after `enhance`, since enrichment adds tours and AI
   surfaces the deterministic gates do not check. `quick` at minimum, `full`
   before publication.

It does not run in CI. It needs a served projection and a real browser;
`gui-plan-check` remains the only CI-side GUI check.

## Commands

Everything goes through the control plane so runs are serial and land on the
testboard.

```bash
# local, the corpus's own projection for this slug
python3 scripts/control.py run assemble --slug <slug>
python3 scripts/control.py run crawl --slug <slug>                 # quick (default)
python3 scripts/control.py run crawl --slug <slug> --profile full  # no budget; minutes on a small subject, hours on VS Code

# local, an explicit projection directory (not the corpus default)
python3 scripts/control.py run assemble --slug <slug> --projection <dir>
python3 scripts/control.py run crawl --slug <slug>

# remote, the published site (no slug, no assemble step)
python3 scripts/control.py run crawl --url https://<host>                 # quick
python3 scripts/control.py run crawl --url https://<host> --profile full
```

`--no-mobile` disables the mobile Playwright project (`CRAWL_MOBILE=0`) when
only the desktop pass is wanted. `CRAWL_PARAMS=<json>` names features
deliberately switched off for this version (`{"declared_off": ["lens:design",
"entry:tours", "surface:review"]}`); a declared-off feature is expected absent
and its presence is the finding. `--dry-run` on any `run` prints the command
and environment without starting anything, useful for checking a
slug/url/profile combination before it spends real time.

## Reading the result

A run against a build that predates the selector contract (no `nav-state`
element) is reported as LIMITED with one `contract.absent` coverage line, never
as green; only a build carrying the contract gets the full suite. Every run
also writes `discovery.json` beside `run.json`: what the build exposed (entry
points, lenses, tours, question routes, sample sizes), for comparing versions
without re-deriving them.

`control.py run crawl` from the CLI waits for the run to finish and then
renders `REPORT.md` next to `run.json` in the run directory via
`scripts/crawl-report.py` (this is the CLI's own follow-up step; the HTTP API
stays fire-and-forget and does not do this). To render or re-render a report
by hand: `python3 scripts/crawl-report.py <run-dir>` or
`python3 scripts/crawl-report.py --latest`.

`REPORT.md` opens with one plain paragraph: what is solid, what is broken,
whether the subject is demoable today. Findings follow, grouped by rule id
(`surface.*`, `graph.*`, `journey.*`, `tour.*`, `reach.*`, ...), each with
severity, instance count and up to five examples, then coverage lines, then a
per-case table. Read the findings by rule id first: one broken selector or one
dropped reset can produce many instances of the same rule across many cases,
and the grouping is what shows that instead of thirty separate-looking rows.

## Roles

- **Running and digesting is Sonnet's job**, through the control plane,
  producing the digest via `crawl-report.py`. The runner executes and
  reports; it does not interpret.
- **Analysis of what the run found belongs to the orchestrating session.**
  Never the other way around: a runner that starts editorializing about
  severity or root cause has stepped outside its role.

## Harness bugs before product defects

A crawl finding can mean the product is broken, or it can mean the crawl's
own expectation model is wrong. Check which before reporting either way: a
harness defect (a selector that no longer matches, a predicate that
mis-derives an expectation from the manifest) is fixed first, silently, and
only then does a rerun's findings get reported as product defects. Reporting
a harness bug as a product regression wastes the reader's time and erodes
trust in every report after it.
