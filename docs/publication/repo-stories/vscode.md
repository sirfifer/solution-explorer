# Repo story: microsoft/vscode

Investigated 2026-08-25 with `/repo-story`. Decides `policy` in
`demos/registry/vscode.json`.

## Verdict

**`follow: pinned`, `pin: <latest 1.x.y release tag>`**, currently `1.134.0`.

The reason is not that `main` is unsafe. It is that a demo we will show
repeatedly, and spend a real enrichment budget on, should sit on a version that
does not move underneath it.

## Evidence

**Default branch is `main`.**

    git ls-remote --symref https://github.com/microsoft/vscode.git HEAD
    ref: refs/heads/main    HEAD

VS Code's `main` is a development branch, but a heavily gated one: required
checks, review, and a very large team working on it continuously. It is not the
kind of `main` that sits broken for days. We analysed it at `1be3e735` and got
100% coverage with zero parse gaps, a clean lint, and 13 of 13 crawl checks
green, so it is demonstrably analysable.

**Releases are frequent and current.** Real release tags are `1.x.y` shaped:

    1.131.0  1.132.0  1.132.1  1.133.0  1.134.0

with `release/1.135` already cut, so `1.134.0` is one release old at most. This
is a monthly cadence, not a stale tag from last year.

**`latest-tag` is unusable on this repo, and that is a finding.** The registry's
`latest-tag` mode sorts with `git ls-remote --tags --sort=-v:refname`, which on
this repo returns:

    vsda-v1.39.1
    v14
    v1.19.3
    v0.45.1

None of those is a VS Code release. The repo carries several unrelated tag
namespaces (`vsda-*`, an old `v0.x` line, component tags), and version-sort
across all of them picks a winner from the wrong family. Following `latest-tag`
here would silently analyse something ancient. Filed against `resolve_ref` in
`scripts/demo-site.py`; until it is fixed, `latest-tag` should not be used on any
subject without checking what it actually resolves to.

## Why pinned rather than default-branch

Three reasons, in order of weight:

1. **Reproducibility.** A tag does not move. Following `main` means the map, the
   screenshots, and the enrichment all describe a commit that no longer exists by
   the time anyone looks. A pinned demo can be regenerated identically a year
   from now.
2. **The enrichment budget.** A full run is a real amount of the weekly
   subscription allowance. Spending it on a moving target means the result is
   stale the moment it lands and cannot be compared against a later run, because
   both the tool and the subject moved.
3. **The story.** "This is VS Code 1.134.0" is a stronger claim than "this is
   whatever was on main that afternoon". It is a version Microsoft shipped to
   millions of people.

The cost is being at most one release behind, which for a monthly cadence is a
few weeks. That is a good trade for a demo.

**Worth stating plainly:** our tool reads structure, it does not build or run the
code, so a broken build would not necessarily produce a bad map. The health
argument here is about the demo's credibility and reproducibility, not about
whether the analyser would cope.

## Expected signature of a healthy fetch

- resolved ref matches `^1\.[0-9]+\.[0-9]+$`
- the resolved SHA is reachable from `main`
- analysis reports 100% coverage with 0 gaps
- `census.parser_degraded` does not fire

## What would change this

- VS Code moving to a different release model, or tags becoming irregular.
- A demo requirement for genuinely current code, which would make
  `default-branch` right and reproducibility the thing we give up.
- `resolve_ref` learning to filter tag namespaces, which would make `latest-tag`
  usable and remove the need to bump `pin` by hand each release.

## Tuning log

| Date | Round | Outcome |
|---|---|---|
| 2026-08-25 | 1 | First application of the skill. Found the `latest-tag` sort defect, which the procedure's step 4 surfaced by asking what the tags actually are rather than trusting the mode name. |
