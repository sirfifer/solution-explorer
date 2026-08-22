# Handoff: the SysCorpus demo program

**If you are a new session, this document is your only required reading.**
Everything you need is here or linked from here. Read "Start here" first, then
the rest of this file, then follow the links only as you need them.

Last updated **2026-08-22**, after the Enrichment Engine landed (PR #105).
`main` is green at `bfbc3fd`.

---

## Start here

### What we are trying to do

Solution Explorer analyzes a codebase and produces a navigable architecture map:
components, relationships, capabilities, data entities, findings, and a viewer
that renders all of it. It is **being built to sell**, and the demo program is
its shop window.

The demo program is a maintained register of well-known open-source codebases
mapped by the product, published on `syscorpus.com`, refreshed weekly from the
owner's Mac Studio, with every refresh feeding fixes back into the tool. Wave 1
is **VS Code, then Home Assistant Core, then Kubernetes**, one at a time,
iterating until each is right before starting the next.

The whole bet is that **a map can be trusted**. That is why so much of what
follows is about instruments, gates and honest gaps rather than features. A map
that is confidently wrong is worse than no map, and most of the hard-won lessons
in this document are variations on that one theme.

### Where it has got to

Read this table as the story, in order. The detail for each line is further down
this file.

| Stage | State |
|---|---|
| Six prerequisites | **Done and merged** (PRs #96, #97, #98) |
| N1, the calibration run | **Done** 2026-08-19. Three personas, measured before and after. PR #100 |
| N2, VS Code pre-flight | **Done** 2026-08-20. Viable on every axis measured |
| The demo harness | **Built.** `scripts/demo-site.py`: fetch, analyze, enhance, validate, diff, deploy, report |
| The Enrichment Engine | **Built, and has never been run for real.** PR #105 |
| Demo one, VS Code, end to end | **Not done.** Blocked, see below |
| Publishing anything | **Parked by the owner.** No Cloudflare, no domains, no DNS, no deploys |

**The Enrichment Engine is the big recent thing and the thing most likely to
matter to you.** It is the permanent process by which every subject goes from
deterministic fact to something a person is drawn into. It is a ladder:

```
P0  deterministic foundation   (no AI)      structure, symbols, importance ranking
P1  orientation                (Fable)      what is this, who reads it, the criteria
P2  the ladder    2a bulk      (Sonnet)     everything, weighted by importance
                  2b escalated (Opus)       only the items the contract failed
                  2c residue   (Fable)      resolve, or declare an honest gap
P3  adjudication               (Opus)       verify passes, grounding spot-checks
P4  synthesis                  (Fable)      tours, narrative, lenses, work orders
P5  determination              (Fable)      done or not, and the Run Report
```

Every item ends in exactly one terminal state: `grounded@sonnet`,
`grounded@opus`, `grounded@fable`, or `honest-gap`. A claim that cannot cite
evidence a mechanical validator can check is not an answer. What three rungs
cannot establish becomes a visible "this could not be determined, and here is
why" in the product, never a faked answer.

It is opt-in (`analyze.py enhance --ladder`), the default path is byte-for-byte
unchanged with the flag off, and both golden corpora prove it.

### What to do next

**Read `docs/publication/ENRICHMENT-INTEGRATION.md` first.** The engine is
built, but most of what it produces does not yet reach a person, and one of its
findings is a blocker that would have silently ruined demo one: the harness
projects the bundle BEFORE it enriches and never re-projects, so it would publish
an unenriched map while every gate approved it. That plan is the current unit of
work.

**After that, there is exactly one thing next, and it is a decision, not a task:
the first real ladder run on VS Code.** Nothing in the engine has ever invoked a
model. The whole thing was built and tested against an injectable seam with
canned responses, so it cost nothing. The first real run spends the owner's
Claude Max usage, and section N3a below has the exact command and the projected
scale.

**Do not run it without the owner explicitly saying so in this session.**

If the owner has said so, run it, then read the Run Report it writes and report
what actually happened, including what the determination said and what the
census looks like. That output is the point; the run is not the deliverable.

If the owner has NOT said so, the useful unblocked work is, roughly in order of
value:

1. **The findings-to-issues filer** (`DEMO-PROGRAM.md` 5.2). Specified, not
   built. Turns parser findings into deduplicated GitHub issues.
2. **The generated hub and the launchd schedule** (`DEMO-PROGRAM.md` 4.3, 4.4).
   Buildable and testable locally; only the deploy needs Cloudflare.
3. **Cards M2, M3 and M4**, cross-repo edges (section N4 below). The
   differentiator, and currently invisible because it has no cards at all.

Bring the owner a decision packet rather than guessing, per the working
agreement at the end of this file.

### The rules that are not negotiable

These have all cost real time. Sections below give the evidence for each.

1. **Environment first, every time.** `python3 -m venv .venv-wt && .venv-wt/bin/pip
   install -e ".[all,dev]"`. A venv without tree-sitter silently falls back to
   regex parsers and **every number you produce will be wrong**. It has already
   caused one bogus 989-symbol diff and silently skipped a guard that would have
   caught two real failures.
2. **No real model invocation without the owner's say-so.** Every phase works
   against the injectable `Invoker` seam in `analyzer/enrich/engine.py`. Build and
   test with canned responses and `--dry-run`. If you believe a real invocation is
   unavoidable, stop and ask.
3. **No Cloudflare, no deploys, no domains, no DNS.** Parked by the owner.
4. **No regression, proven not asserted.** Run
   `scripts/golden-corpus.py check flask` AND `check fastapi` at every task
   boundary. Both must report no drift.
5. **Know your baselines and do not hide behind them.** In a **worktree**,
   pytest has exactly one pre-existing failure
   (`test_pruned_directory_row_stands_in_for_its_contents`, because `.git` is a
   file in a worktree). In the **primary checkout** there are zero failures. The
   viewer has 86 vitest failures across 11 files, environment-only: capture the
   failing FILE set before and after and diff the lists. Any new failing file is
   yours.
6. **Cost figures are API-equivalent units** the CLI reports, metered against the
   owner's Claude Max subscription. **Never present them as money spent.**
7. **No em dashes or en dashes** as sentence interrupters, anywhere, including
   code comments. `.claude/rules/writing-style.md`.
8. **Hold confirmations to the same standard as refutations.** The three defects
   that survived one delegated build were all checks that passed, so nobody
   looked. During the Enrichment Engine build, five defects were found by reading
   the artifact rather than the test result, and two of them were hiding behind
   green tests that asserted the wrong thing.

### The map of the documents

Read these only when you need them. This file is the entry point.

| Document | What it is | When you need it |
|---|---|---|
| `docs/publication/ENRICHMENT-ENGINE.md` | **Design of record** for the enrichment ladder, the completeness contract, the Run Report | Before touching anything in `analyzer/enrich/` |
| `docs/publication/ENRICHMENT-ENGINE-BUILD.md` | The build plan, T1 to T12. **All executed**, PR #105 | Historical. Useful for the module map and canonical data shapes |
| `docs/publication/ENRICHMENT-INTEGRATION.md` | **Plan of record** for wiring the engine into the existing tech, with the blockers before demo one | **Now.** This is the current unit of work |
| `DEMO-PROGRAM.md` | The plan, the eleven-subject register, execution design, the findings loop, commercial framing | Building any part of the demo program |
| `DEMO-PREREQUISITES.md` | The six prerequisites, what each surfaced, the multi-repo correction | Understanding why the demo order is what it is |
| `docs/publication/PREFLIGHT-MEASUREMENTS.md` | The VS Code pre-flight numbers | Sizing a subject |
| `docs/quality/COMPREHENSION-REVIEW.md` | The comprehension instrument and rubric | Running or scoring a persona sitting |
| `docs/remediation/COMPREHENSION-STUDY-2026-08-17.md` | Where this whole thread started | Context on why the trust work exists |
| `DISCLOSURE-POLICY.md`, `LICENSE-REVIEW.md`, `PUBLICATION-METADATA.md` | What a publication owes its subject | Anything published, or any consent question |
| `docs/commercial/VALUATION-SNAPSHOT.md` | Commercial framing | Milestones |
| `tests/fixtures/enrichment-run/REPORT.md` | A **reference Run Report** from a full mock run | Seeing what the engine actually produces, for free |

---

## State of the world

| Thing | State |
|---|---|
| `main` | Green. Comprehension fixes, publish gate, preview gate, comprehension instrument, language-tier fix all merged |
| Live demos | `solution-explorer.unamentis.org` and `um-arch.unamentis.org`, both redeployed and verified carrying the new engine output |
| `wt/demo-program` branch | The planning docs. Merge it or work from it; it is documentation only |
| Domain | `syscorpus.com` (owner also holds `.org`). DNS and Cloudflare projects not yet created |
| Demo harness | Built. `scripts/demo-site.py`, with the ladder plumbed through `enhance` and the `enrichment_quality` gate reading the contract census and adjudication verdicts rather than the form scorer |
| Enrichment Engine | Built, never run for real. `analyzer/enrich/` P1 through P5, `--ladder` opt-in. The first real run is owner-gated |
| VS Code pre-flight | Measured and viable. 668 published files against a 20,000 ceiling, 136 s cold, 0.10% detect-only on code lines. `docs/publication/PREFLIGHT-MEASUREMENTS.md` |
| VS Code clone and store | Already on disk at `/Volumes/Studio/dev/.scratch/n2/`, ~1.2 GB. Reusable for demo one; reproducible if deleted |
| Live demo data | Fixed 2026-08-21. The Live overlay had been serving 2026-02-23 data that looked fresh; UnaMentis/unamentis#123 removed the stale committed file. Both front doors now report 254 |

Decided, do not re-litigate (owner decisions 2026-08-18):

- **Wave 1 is VS Code, then Home Assistant Core, then Kubernetes**, one at a
  time, iterating until each is right before starting the next.
- **One Cloudflare Pages project and subdomain per demo**, plus a separate
  generated hub. Driven by the free plan's 20,000-files-per-site limit, which is
  per site and would otherwise be shared across every demo.
- **GitHub Issues as the deduplicated findings inbox**, `TASKS.md` remains the
  campaign tracker, with an explicit seam: the card is the plan of record, the
  issue is the receipt.
- **Enrichment keeps using the `claude` CLI.** The API-key invoker was declined,
  so the loud-failure requirement and the hub's last-successful-refresh date are
  load bearing rather than nice to have.
- **Two tracks with a hard gate.** Published demos must fairly represent their
  subject; capability-forcing targets stay local or gated. `DEMO-PROGRAM.md`
  section 2 has the gate.

## Traps that already cost time. Read these.

1. **A venv without tree-sitter silently falls back to regex parsers.** It cost
   a bogus golden diff showing 989 phantom symbol losses, and it silently
   *skipped* the parity guard that would have caught two real failures, because
   the parity snapshots are pinned to the tree-sitter tier and skip loudly on
   the regex lane. **Always `pip install -e ".[all,dev]"` before trusting any
   local diff or test posture.**
2. **Know the posture for the checkout kind you are in, and re-measure it.**
   As of 2026-08-22 on `main` at `bfbc3fd`: a **normal checkout** is 1928 passed,
   4 skipped, 1 xfailed, **0 failed**. A **worktree** checkout is the same except
   for one failure, `test_pruned_directory_row_stands_in_for_its_contents`, which
   asserts that the `.git` *directory* contributes exactly one pruned-directory
   ledger row; in a worktree `.git` is a file, so the row cannot exist.
   Environment-only, and it does **not** indicate a regression. These counts move
   every time tests land, so measure yours before you change anything and compare
   against that, not against this number. An older handoff recorded "1451 / 3",
   measured in a venv without tree-sitter, which is trap 1 producing a wrong
   baseline that then looked authoritative for weeks.
3. **The viewer's 86 local test failures are environment-only** (`localStorage`
   unavailable in the local Node). They pass in CI. Do not chase them, and do not
   let a real failure hide among them: capture the failing FILE set before and
   after a change and diff the two lists.
4. **A pure id-based diff reports any id-scheme change as total churn, and every
   pathway agreed with it.** The UnaMentis publication once showed 254 "New
   component discovered" rows and 256 removals, of which roughly 250 were the
   same components re-identified with a `unamentis/` prefix and about six
   changed for real. Verified 2026-08-19, see `ORCHESTRATOR-FINDINGS.md`.
   **Resolved in PR #100.** `analyzer/project/id_normalization.py` now
   recognises a re-identification (same component, new id scheme) as its own
   change kind instead of a paired add and remove, so the projection diff no
   longer reports a namespace migration as churn. The lesson still stands for
   the next id-scheme change: a diff showing mass adds and removes in lockstep
   is worth checking against `id_normalization.py`'s re-identification logic
   before assuming it is real churn. This is the same shape as the
   989-phantom-symbol-losses trap above.
5. **Enrichment lives in the store; the bundle only carries it if you project
   AFTER enhancing.** `analyze` projects, `enhance` writes store rows, and
   nothing re-projects on its own. The harness's `refresh` gets this order wrong
   today (see `ENRICHMENT-INTEGRATION.md` I1), and the failure is silent: the
   deployed bundle simply has no `ai_enhance`, no tours and no honest gaps, and
   every gate agrees it is fine because they check either the enhance report or
   internal consistency, both of which hold when nothing is enriched. Verified
   empirically 2026-08-22. **If you touch the analyze/enhance/publish order,
   check the manifest itself, not the report.**
6. **Fixing a classification can remove an accidental exclusion elsewhere.**
   Stopping test directories being typed `api-server` produced 68 bogus
   "unreferenced" findings on FastAPI, because the unreferenced rule had been
   skipping them only as a side effect of the mislabel. The golden corpus caught
   it. Run `golden-corpus.py check` on both corpora after any derive change.

## What to do next, in order

### N1. The calibration run. DONE, 2026-08-19

Run at `docs/quality/runs/unamentis/2026-08-19/`, baseline at
`.../2026-08-17/`, raw persona material at
`/Volumes/Studio/dev/.evidence/solution-explorer/persona-runs/20260819/`.

```
P1 senior engineer, unfamiliar language   11/24 -> 17/24  (+6)
P2 non-coding executive                   12/24 -> 13/24  (+1)
P3 staff engineer, AI power user           6/24 -> 18/24  (+12, lower bound)
Trust incidents: 17 -> 8
```

Read `REVIEW.md` in the run directory before quoting any of that. The headline
caveats: the baseline is a floor because P3's 2026-08-17 findings document did
not survive; P2, the commercially important persona, moved by one point; and
advertised paths remains the weakest dimension at 2, 0 and 2.

**Do not take a persona's interaction claim at face value.** Of 8 such claims
checked in this run, 3 were false and 2 were harness artifacts; only 3 were
real. Of 3 data and consistency claims checked, all 3 verified exactly. Agent
personas read data reliably and perceive interfaces unreliably. One of the
false claims was confirmed by the orchestrator against the wrong file and later
retracted, so hold confirmations to the same standard as refutations.

**Staffing is solved and reusable.** `scripts/comprehension-sitting.sh` gives a
persona isolation by construction rather than by instruction: a working
directory outside the repository, browser-only MCP, no skills, and a deny list
removing Read, Bash, Grep, Glob, WebFetch, WebSearch and Agent. Verified: the
persona has only `ToolSearch`, `Write`, `TodoWrite` and the browser. Personas
and briefs are in `docs/quality/personas/`. Reuse both for every subject.

**The charter's "B+ maps to 17 to 19 of 24" is wrong** and should be struck. The
same sittings score 11, 12 and 6. A letter grade and the rubric measure
different things.

### N2. Pre-flight measurement. DONE for VS Code, 2026-08-20

Results in `docs/publication/PREFLIGHT-MEASUREMENTS.md`. VS Code is comfortably
viable on every axis measured, and the analysis completed cleanly twice with no
errors.

Home Assistant Core and Kubernetes were **deliberately deferred**: measuring
three subjects before demo one exists is premature, and their numbers can be
taken when their turn comes.

**One question remains open and it needs an owner decision before generating:**
`enhance --dry-run` reports 1,446,236 prompt tokens but models neither output
tokens nor cost. Enrichment runs on the owner's `claude` subscription rather
than an API key, so this is a real call about when to spend that usage, not a
line item. It can only be settled by an actual `enhance` run.

### N3a. The Enrichment Engine. BUILT, 2026-08-21, not yet run for real

T1 through T12 of `ENRICHMENT-ENGINE-BUILD.md` are complete and merged. The
ladder runs orientation through determination against a real store and writes a
Run Report. `--ladder` defaults off and the projection is unchanged with it off,
proven by both golden corpora at every task boundary.

**No model has been invoked.** Every phase was built and tested against the
injectable invoker seam with canned responses. The reference Run Report at
`tests/fixtures/enrichment-run/` was produced by a full-pipeline mock run and
costs nothing to regenerate.

**Planned against the real VS Code store, dry run, 2026-08-21:** 55 partitions
for rung 2a, an orientation prompt of ~5,800 tokens, a synthesis prompt of
~74,700 tokens, 3 criteria, 1 forced round. Zero invocations, zero cost.

**The first real run is owner-gated and is the N2 open question made concrete.**
The exact command is in PR #105's description. It will spend real Claude Max
usage; nobody should run it without the owner saying so.

Tier bindings are now configuration, not architecture (owner direction,
2026-08-21). A rung is bound to a SOURCE plus an optionally pinned model, and
`source:auto` leaves the model unpinned so that source routes the call itself.
Only the `claude` CLI provider ships; adding a lab or an aggregator is a
registration in `analyzer/enrich/models.py`, not a refactor.

### N3. The demo harness and demo one

`scripts/demo-site.py` per `DEMO-PROGRAM.md` section 4.2, the registry per 4.1,
the launchd schedule per 4.3, the generated hub per 4.4. Then VS Code end to
end, deployed as a **private preview first** using
`infrastructure/preview-gate/`, and public only after it passes the graduation
gate and a comprehension review.

**Blocked on the owner, and these gate the deploy half of N3:**

1. Create the Cloudflare Pages project for demo one.
2. Set `PREVIEW_PASSCODE` for `infrastructure/preview-gate/`.
3. Decide when to spend the enrichment run (see N2 above).

Note that the harness, registry, hub generator and launchd unit can all be built
and tested locally before any of those exist. Only the deploy needs them.

## Deferred to the Wave 1 retrospective

**The rule (owner decision, 2026-08-20).** Do not be shy about cheap
performance, quality-of-life and fine-tuning work; do it as it comes up. But
work whose value is *hard to establish* waits until we have more data, meaning
late in Wave 1 or at the end of it, when a wider sampling of projects makes it
possible to decide what is actually worth doing rather than guessing from one
subject.

**Why this rule earned its place immediately.** The search index looked
demo-blocking on 2026-08-20: 61 MB across 84 shards, fetched sequentially. A
restructure was scoped and approved. Measurement then showed the origin already
serves brotli (2.9 MB over the wire, not 61 MB), that search returns usable
results in 451 ms because it matches against the already-loaded architecture
while shards enrich it afterwards, and that the obvious two-tier design was not
even viable, because matching needs the `text` field so it cannot be deferred.
The restructure was dropped for two small fixes. One subject could not tell the
difference between "expensive at scale" and "expensive-looking on paper".

**How to use this register.** Each item records what we know now and, more
importantly, **what evidence would settle it**. At the Wave 1 retrospective,
answer them from three subjects rather than one.

| Deferred item | What we know | What would settle it |
|---|---|---|
| Search index restructure | Not warranted on VS Code. Brotli makes it ~2.9 MB on the wire; results are usable in 451 ms. Client-side memory and Fuse index-build cost at 167,693 entries were never measured | Whether any Wave 1 subject makes search slow *in the browser*, and the measured index-build time and memory at the largest subject's scale |
| External dependency detection completeness | Only the honest labelling was fixed. Detection is still a hardcoded 18-domain match that counts GitHub from a CI script and misses Unleash and LiveKit entirely | Whether the same class of miss recurs across three unrelated subjects, which would show it is systemic rather than a UnaMentis quirk. Also whether declared-dependency manifests are a better signal than URL matching |
| Cross-surface agreement gates | `ai.json`, the manifest and the admin summary each passed their own validity checks while contradicting each other. Two of this run's deepest defects shared that signature | Whether disagreements recur on other subjects, and which surface pairs are worth gating. Cheap to build, and unlike the comprehension review it could run every weekly refresh |
| Classification accuracy audit | Does not exist. `DEMO-PROGRAM.md` 5.3 already says to specify it from what the first demo's review finds by hand, rather than guessing now | The by-hand findings from demo one, which is exactly the wider-sampling logic applied to a smaller scope |
| Compact index encoding | Measured at 47% smaller uncompressed, but brotli already captures the same redundancy, so the benefit is client-side only | Only worth revisiting if browser memory or parse time turns out to be the real constraint at Wave 1 scale |

**What is NOT deferred**, because it is cheap and its value is obvious: the
bounded-concurrency shard fetch and the partial-results indicator; anything that
stops a surface asserting something it cannot support; and any defect a persona
or a gate reproduces.

### N4. Card M2, M3 and M4

Multi-repo has M1 only (composition, no cross-repo edges), and M2, M3 and M4
have **no cards in TASKS.md at all**. Cross-repo edges are the differentiator, so
this is more important than its current invisibility suggests. Needed before the
Supabase demo. See `DEMO-PREREQUISITES.md` section 1.

## Delegation: who should do what

Opus should not do work that gains nothing from Opus. Rough routing, with the
reason, because the reason is what generalises:

| Work | Model | Why |
|---|---|---|
| Retrospective scoring of the 2026-08-17 artifacts against the rubric | **Sonnet** | Reading given artifacts and applying an explicit rubric with anchors. Mechanical once the rubric is fixed |
| Persona sittings (each persona) | **Sonnet** | The persona is deliberately not an expert. A cheaper model is arguably a *better* persona for P2, the non-coding executive. Each needs a fresh context, which is the real requirement |
| Pre-flight measurement, the six numbers | **Sonnet** | Run commands, record numbers, no judgement |
| The three-subject reconnaissance | **Sonnet** to gather, **Opus** to interpret | Gathering is mechanical; deciding what a structural surprise means for the harness design is not |
| `scripts/demo-site.py` harness | **Sonnet** | Orchestration over CLIs that already exist, against a written design. Well-specified plumbing |
| Registry entries, hub generator, launchd unit | **Sonnet** | Templated, specified |
| Findings-to-issues filer (fingerprints, dedup, auto-close) | **Sonnet** | Specified in `DEMO-PROGRAM.md` 5.2 |
| Answer key for a subject | **Opus** | Deciding what is true about an unfamiliar codebase, and what cannot be settled and must be marked unscoreable. Wrong keys are worse than missing ones |
| Orchestrator verification and the instrument retro | **Opus** | Adversarial judgement about our own product |
| Interpreting a golden or projection diff | **Opus** | Intended improvement or regression is exactly the judgement call that goes wrong quietly |
| Classification accuracy audit design | **Opus** | New instrument, no precedent to follow |
| M2 cross-repo edge design | **Opus** | Architecture with a parity burden |
| Anything touching the publish gate, the preview gate, or consent | **Opus** | Legal, ethical and security surface where a quiet mistake is expensive |

Rule of thumb for anything not listed: **if the work is "follow this written
design", delegate it; if the work is "decide what this means", do not.**

Whoever delegates keeps the verification. A delegated task is not done because
it reports done: check the tests, check the diff, and check the claim against
the artifact.

## Verification commands

```bash
# ALWAYS first, in any fresh checkout or worktree. Without tree-sitter the
# parsers silently degrade and every number below is wrong.
python3 -m venv .venv-wt && .venv-wt/bin/pip install -e ".[all,dev]"

# Posture. Measure BEFORE you change anything and compare against your own
# baseline, not against a number written in a document.
.venv-wt/bin/python -m pytest tests/ -q
.venv-wt/bin/python -m ruff check analyze.py analyzer/ scripts/ tests/
node --test infrastructure/preview-gate/*.test.mjs
cd viewer && npx tsc --noEmit && npx eslint src/ && npx vitest run

# No regression, proven. Both, every time, at every task boundary.
.venv-wt/bin/python scripts/golden-corpus.py check flask
.venv-wt/bin/python scripts/golden-corpus.py check fastapi

.venv-wt/bin/python scripts/gui-plan-check.py
.venv-wt/bin/python scripts/validate-publication.py <bundle-dir> --require
.venv-wt/bin/python scripts/comprehension-score.py score <run-dir>
```

**The enrichment ladder, without spending anything.** Every one of these invokes
no model:

```bash
# Plan the whole ladder against a real store. Zero invocations, zero cost.
.venv-wt/bin/python analyze.py enhance <root> --store <store.db> --ladder --dry-run \
    --run-dir /tmp/ladder-dryrun

# See what the engine actually produces, for free: the reference Run Report from
# a full-pipeline mock run.
cat tests/fixtures/enrichment-run/REPORT.md

# Check the bundle really carries the enrichment, not the report's claim about it.
# See ENRICHMENT-INTEGRATION.md I1 for why this is the check that matters.
python3 -c "import json,sys; m=json.load(open(sys.argv[1])); \
  print('tours:', len(m.get('tours') or []), \
        '| honest_gaps:', 'yes' if 'honest_gaps' in json.dumps(m) else 'no')" \
  <bundle-dir>/manifest.json
```

**A real ladder run spends the owner's Claude Max usage and requires his
explicit say-so in your session.** The command is in PR #105 and in N3a below.

## Reference

- `DEMO-PROGRAM.md`: the plan, the eleven-subject register, execution design,
  the findings loop, the commercial framing.
- `DEMO-PREREQUISITES.md`: the six prerequisites, what each surfaced, the
  multi-repo correction, the demo-order reasoning.
- `docs/quality/COMPREHENSION-REVIEW.md`: the instrument.
- `DISCLOSURE-POLICY.md`, `LICENSE-REVIEW.md`, `PUBLICATION-METADATA.md`: what a
  publication owes its subject.
- `docs/remediation/COMPREHENSION-STUDY-2026-08-17.md`: where the whole thread
  started.

## Working agreement with the owner

1. **Never surface a decision without the full packet**: the concrete situation
   with fresh evidence, why it matters, three or four real options each with an
   effort estimate and explicit for and against, a recommendation with
   reasoning, and exactly what is being asked. Deliver it as a document, and
   pair it with clickable options, because typing is painful for him.
2. **An analysis request ends at the analysis.** Do not slide from investigating
   into implementing without an explicit go-ahead.
3. **Report honestly.** If a thing is unverified, say so. The whole product is a
   bet that a map can be trusted; the work on it is held to the same standard.
