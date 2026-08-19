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
Nothing of the demo program itself is built yet. The next unit of work is the
calibration run, then pre-flight measurement, then demo one.

## State of the world

| Thing | State |
|---|---|
| `main` | Green. Comprehension fixes, publish gate, preview gate, comprehension instrument, language-tier fix all merged |
| Live demos | `solution-explorer.unamentis.org` and `um-arch.unamentis.org`, both redeployed and verified carrying the new engine output |
| `wt/demo-program` branch | The planning docs. Merge it or work from it; it is documentation only |
| Domain | `syscorpus.com` (owner also holds `.org`). DNS and Cloudflare projects not yet created |
| Demo harness | Does not exist. Designed in `DEMO-PROGRAM.md` section 4 |

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
2. **The true test posture is 1609 passed, 1 failed**, not the "1451 / 3" an
   older handoff recorded, which was measured in that broken environment. The
   single failure is `test_pruned_directory_row_stands_in_for_its_contents`,
   which fails only inside a git worktree (where `.git` is a file, not a
   directory) and passes in CI and in a normal checkout.
3. **The viewer's 86 local test failures are environment-only** (`localStorage`
   unavailable in the local Node). They pass in CI. Do not chase them, and do not
   let a real failure hide among them: capture the failing FILE set before and
   after a change and diff the two lists.
4. **Fixing a classification can remove an accidental exclusion elsewhere.**
   Stopping test directories being typed `api-server` produced 68 bogus
   "unreferenced" findings on FastAPI, because the unreferenced rule had been
   skipping them only as a side effect of the mislabel. The golden corpus caught
   it. Run `golden-corpus.py check` on both corpora after any derive change.

## What to do next, in order

### N1. The calibration run of the Comprehension Review

The charter is `docs/quality/COMPREHENSION-REVIEW.md`. Read the two sections
"Who can be a persona" and "A calibration run" before planning anything: **a
persona must have no exposure to this repository**, which disqualifies the
orchestrating session from the sittings and means each persona is a fresh
context briefed only with its persona, mission, battery and URL.

Three parts:

- **Before**: retrospectively score the 2026-08-17 sitting from its preserved
  artifacts at `/Volumes/Studio/dev/.evidence/solution-explorer/persona-runs/20260817/`
  (three journals, two findings documents, 124 screenshots). Mark
  `"retrospective": true`, and leave any dimension the artifacts cannot support
  as `null` rather than inventing it. This is the baseline.
- **After**: three live sittings against `solution-explorer.unamentis.org`,
  which now carries the fixes.
- **Report**: `scripts/comprehension-score.py compare <after> <before>`, plus a
  `REVIEW.md` with independent verification and the instrument retro.

Outstanding decision for the owner: **how the personas are staffed.** Subagents
(a fresh subagent per persona, never having read the repo) or separate sessions.
The session that wrote this could not do it itself without invalidating the
measurement.

Run directory: `docs/quality/runs/unamentis/<date>/`.

### N2. Pre-flight measurement and the three-subject reconnaissance

`DEMO-PROGRAM.md` section 4.6 lists the six measurements. Analysis only: no
enrichment, no deploy, **no fixing**. Recon is not a fix cycle; record what you
see and fix nothing until the demo whose turn it is. Note the detect-only
language share calculation changed when Java, C# and C/C++ moved to the
full-parsing tier (PR #98), so recompute rather than reusing an old estimate.

### N3. The demo harness and demo one

`scripts/demo-site.py` per `DEMO-PROGRAM.md` section 4.2, the registry per 4.1,
the launchd schedule per 4.3, the generated hub per 4.4. Then VS Code end to
end, deployed as a **private preview first** using
`infrastructure/preview-gate/`, and public only after it passes the graduation
gate and a comprehension review.

Blocked on the owner: creating the Cloudflare Pages projects and setting
`PREVIEW_PASSCODE`.

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

.venv-wt/bin/python -m pytest tests/ -q          # expect 1609 passed, 1 failed in a worktree
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
