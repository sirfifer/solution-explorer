# Pre-flight measurements

The six measurements `DEMO-PROGRAM.md` section 4.6 requires before committing to
a subject. Measured, not estimated. Each row names what produced it.

**Scope note.** Only Visual Studio Code has been measured. Home Assistant Core
and Kubernetes were deliberately deferred: cloning and analysing them before
demo one exists is premature, and their numbers can be taken when their turn
comes. That is a scope reduction, recorded here so it is visible rather than
forgotten.

---

## Visual Studio Code, measured 2026-08-20

Subject: `github.com/microsoft/vscode`, shallow clone at `74d615da22fd`.
Machine: Mac Studio, 36 GB RAM, 14 cores. Environment: `.venv-wt` with
tree-sitter present, which is mandatory; without it the analyzer silently falls
back to regex parsers and every number below would be wrong.

```
.venv-wt/bin/python analyze.py <clone> -o <out> --split --engine v2 --store <db>
```

| # | Measurement | Result | Verdict |
|---|---|---|---|
| 1 | Published file count against the 20,000-file Cloudflare ceiling | **668 files**: 570 data shards, 85 search shards, 7 top-level JSON, 6 app-shell files | **Comfortable.** 3.3% of budget, 19,332 files of headroom, roughly a 30x margin |
| 2 | Wall time, peak memory, store size | Cold **136.5 s**, warm 95.5 s; peak RSS **1.93 GB**; store **656 MB** | **Well inside** the registry's proposed 45-minute budget and this machine's RAM |
| 3 | Detect-only language share against the 25% gate | **0.10% on code lines** (3,671 of 3,858,464). All-lines figure is 21.92% | **Passes easily.** Use the code-only figure; the all-lines number is inflated by JSON and config and would give a false read |
| 4 | Enrichment cost | `enhance --dry-run` reports **1,446,236 prompt tokens** across 55 partitions plus a narrative pass. **No output-token estimate and no dollar figure** | **Open question.** See below |
| 5 | Does `wrangler pages deploy` consume the 500/month build quota? | **No.** Direct upload bypasses the CI build step entirely, so the quota does not apply | **Clear.** Weekly refreshes do not compete with the build limit |
| 6 | Disk footprint | Clone 339 MB + store 656 MB = **~1.0 GB**; 1.2 GB including split output | **Fine** |

**The analysis completed cleanly, twice, cold and warm, exit 0, no errors or
warnings.** Nothing measured here blocks a first VS Code generation.

### The one genuinely open question: enrichment cost

`enhance --dry-run` estimates prompt tokens only. It models neither output
tokens nor cost, so the 1,446,236 figure is an input-side floor.

This matters more than a dollar figure suggests, because **enrichment runs
through the `claude` CLI on the owner's subscription, not an API key** (owner
decision, recorded in the handoff). So the real cost is the owner's usage, and a
1.45M-token run is not something to start without deciding when to spend it.

Resolvable only by an actual `enhance` run. Deliberately not run during
measurement.

### Things worth knowing before generating

- **Line count differs from the plan's figure.** Measured 4,936,720 lines, 570
  components, 15,256 parsed files. The README and plan cite roughly 3.47M lines
  from an earlier measurement, a 42% gap. Not diagnosed. Likely repo growth, and
  the plan's number should be treated as stale.
- **Store size differs too**: 656 MB measured against roughly 420 MB previously
  cited. Same status.
- **A shallow clone yields one commit of activity.** Component and coverage
  numbers are unaffected, but anything depending on commit history, co-change
  pairs, authorship, staleness, will be thin or empty. A real weekly refresh
  needs a decision on how much history to fetch.
- **Warm-run savings are bounded.** Cold 136.5 s to warm 95.5 s, only 30%
  faster, despite zero files re-parsed. Most of the time and memory goes into
  serializing 662 split-output files and the fixed-cost passes, not extraction.
  Caching helps a refresh, but not dramatically.

### Where the artifacts are

The clone, store and split output from this run are at
`/Volumes/Studio/dev/.scratch/n2/`, roughly 1.2 GB. Keeping them saves
re-cloning and re-analysing when demo one starts. Delete freely; they are
reproducible with the command above.

---

## Clone depth, measured 2026-08-20 (N3)

N2 recorded that "a shallow clone yields one commit of activity" and that
history-dependent output "will be thin or empty". Measured properly at the start
of N3, that understates it in the one direction that matters: **the Activity
lens does not come out empty, it comes out populated and wrong.**

Both runs below analyze the **same working tree**, `74d615da22fdd1992966b51551c4ef12ae5c09a4`,
so clone depth is the only variable. Both produced identical structure: 570
components, 15,256 files, 4,936,720 lines, 151,867 symbols, 100% coverage.

| Signal | Shallow, depth 1 | Full history | Consequence of shipping the shallow one |
|---|---|---|---|
| Commits seen | 1 | 146,125 | |
| Distinct authors | 1 | **2,771** | |
| `file_coupling` / `component_coupling` | 0 / 0 | 100 / 100 | Co-change lens empty |
| Components flagged knowledge islands | **567 of 567** | 53 of 567 | Publishes "every component is a knowledge island" about a project with 2,771 contributors |
| Bus factor, min/median/max | 1 / 1 / 1 | 1 / 2 / 11 | Publishes bus factor 1 for all of VS Code |
| Distinct `last_modified` values | 1 | 4,746 | Staleness meaningless |
| Files where `churn == lines_added`, nothing removed | 15,256 of 15,256 | 3,596 | `churn` is really the file's line count |
| Top hotspot | `colorize-fixtures/test-checker.ts` | `src/vscode-dts/vscode.d.ts` | Publishes a ranking of the **largest** files as the most-changed |

The mechanism: a depth-1 clone's single commit is parentless, so `git log
--numstat` reports the entire tree as added. `churn` becomes the file's line
count and `hotspot_score` becomes `churn + 1` (14,010 of 15,256 files exactly).
One author gives `top_author_share = 1.0`, which is above the 0.95
`KNOWLEDGE_ISLAND_SHARE` threshold, so every component trips the flag.

`provenance` does honestly record `shallow: true, commits: 1`, so the data is
labelled. That is not sufficient: the numbers themselves read as real activity,
and this is exactly the defect class that has cost this project the most time, a
plausible wrong answer that passes every machine gate.

### What full history costs

| | Shallow depth 1 | 12-month `--shallow-since` | Full |
|---|---|---|---|
| Clone wall time | (not re-measured) | 20 s | **80 s** |
| Clone disk | 339 MB | 569 MB | **1.4 GB** |
| Commits in `git log --no-merges` | 1 | 22,354 | 146,170 |
| Commits emitting >5,000 file rows | 1 of 1 | **15** | **1** |
| Analysis wall time | 136.5 s cold | (not run) | **208.4 s** |
| Analysis peak RSS | 1.93 GB | (not run) | **1.85 GB** |

**The 12-month shallow clone is the trap option.** It looks like a cheap middle
ground and it is not: its 15 commits emitting more than 5,000 file rows each are
exactly the 16 SHAs in `.git/shallow`, the grafted boundaries. Each one is a
parentless synthetic full-tree add, so it reproduces the depth-1 defect fifteen
times over instead of once. The full clone has exactly **one** commit above
5,000 rows and it is a genuine 2018 commit, not an artifact.

Full history costs **+72 s of wall time and about 1 GB of disk**, and peak memory
went slightly *down*. That is inside the registry's 45-minute budget by a wide
margin.

**Decision: `policy.history: "full"` for every published demo.** Recorded in
`demos/registry/<slug>.json`. A shallow clone is acceptable only for a Track B
capability-forcing target where nobody reads the Activity lens.

Incidental finding, recorded because it will mislead someone later:
`git clone --depth=5000` against this repo did **not** produce a shallow
repository. Reproduced three times with packet traces; the client sends
`deepen 5000` and the server returns a `shallow-info` section, but `index-pack`
runs with an empty `--shallow-file` and no boundary is applied. `--depth=100`
against the same server in the same session behaved normally. So depth-based
bounding is not dependable here; use `--shallow-since` or a full clone.
