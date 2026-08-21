# Handoff: the SysCorpus demo program

Written 2026-08-18 for a fresh session. Self-contained: everything needed to
pick up is here or linked from here. Read this first, then
`DEMO-PROGRAM.md` (the plan and the register) and `DEMO-PREREQUISITES.md`
(what had to be true first, and what it surfaced).

## The one-paragraph situation

Solution Explorer is being built to sell, and the demo program is its shop
window: a maintained register of well-known codebases mapped by the product,
published on `syscorpus.com`, refreshed weekly from the owner's Mac Studio, with
every refresh feeding fixes back into the tool. The plan, the project register
and the execution design are agreed and decided. **All six prerequisites are
built and merged** (PRs #96, #97, #98; `main` is green at `71e7a8d` or later).
**N1 (the calibration run) and N2 (pre-flight measurement for VS Code) are both
complete**, merged in PR #100 on 2026-08-21. Nothing of the demo program itself
is built yet. **The next unit of work is N3: the demo harness and demo one.**

## State of the world

| Thing | State |
|---|---|
| `main` | Green. Comprehension fixes, publish gate, preview gate, comprehension instrument, language-tier fix all merged |
| Live demos | `solution-explorer.unamentis.org` and `um-arch.unamentis.org`, both redeployed and verified carrying the new engine output |
| `wt/demo-program` branch | The planning docs. Merge it or work from it; it is documentation only |
| Domain | `syscorpus.com` (owner also holds `.org`). DNS and Cloudflare projects not yet created |
| Demo harness | Does not exist. Designed in `DEMO-PROGRAM.md` section 4. **This is the next thing to build** |
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
2. **The current test posture in a normal checkout is 1642 passed, 4 skipped, 1
   xfailed, 0 failed** (verified 2026-08-20), not the "1451 / 3" an older
   handoff recorded, which was measured in that broken environment. A worktree
   checkout (where `.git` is a file, not a directory) can still behave
   differently from a normal checkout, but the previously-recorded
   `test_pruned_directory_row_stands_in_for_its_contents` failure specific to
   that setup no longer reproduces.
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
5. **Fixing a classification can remove an accidental exclusion elsewhere.**
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
# ALWAYS first, in any fresh worktree
python3 -m venv .venv-wt && .venv-wt/bin/pip install -e ".[all,dev]"

.venv-wt/bin/python -m pytest tests/ -q          # expect 1642 passed, 4 skipped, 1 xfailed, 0 failed in a normal checkout
.venv-wt/bin/python -m ruff check analyze.py analyzer/ scripts/ tests/
node --test infrastructure/preview-gate/*.test.mjs
cd viewer && npx tsc --noEmit && npx eslint src/ && npx vitest run

.venv-wt/bin/python scripts/golden-corpus.py check flask
.venv-wt/bin/python scripts/golden-corpus.py check fastapi
.venv-wt/bin/python scripts/gui-plan-check.py
.venv-wt/bin/python scripts/validate-publication.py <bundle-dir> --require
.venv-wt/bin/python scripts/comprehension-score.py score <run-dir>
```

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
