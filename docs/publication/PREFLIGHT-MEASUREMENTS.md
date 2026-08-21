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
