# Prerequisites before demo work starts

Written 2026-08-18, after a review of the demo program plan against the actual
state of the code. Companion to `DEMO-PROGRAM.md`. This is analysis; nothing
here is built.

## The short version

Six prerequisites, one of which is bigger than the two the owner named. Neither
multi-repo nor Java is a prerequisite for Wave 1, and one claim in the program
plan was wrong and is corrected below. Realistic time to ready is about a week,
not a day, and most of it is one merge plus one new instrument.

Recommended order of the three demos changed too, on reflection: VS Code, then
Home Assistant, then Kubernetes, with a reconnaissance pass over all three
before any of it.

---

## 1. Correction to the program plan

The plan said multi-repo emits no unified coverage ledger, so a multi-repo demo
would show "Coverage unavailable", and that this blocks Supabase. That is half
wrong and the half that is wrong matters.

There are TWO multi-repo paths:

- The **legacy `--config` path** (`analyzer/derive/multi.py`, 172 lines) merges
  repos into one architecture. It carries no coverage ledger, no capabilities,
  no entities, no rules, no activity, no correlations. Both UnaMentis
  installations use this path, which is why they show "Coverage unavailable".
- The **M1 `--solution` path** (`analyzer/solution/`, DONE 2026-07-19) projects
  each member as a full, unchanged single-repo projection under
  `members/<slug>/`. Every member therefore keeps its complete coverage ledger,
  capabilities, entities and rules, and the solution layer deliberately never
  blends a coverage denominator across repos (a recorded design decision).

So coverage is not the multi-repo blocker. The real blocker is worse and
simpler: **there are no cross-repo edges.** `analyzer/solution/__init__.py`
states it outright: "M1 is composition only. There are NO cross-repo edges, NO
merged store". M2 (cross-repo HTTP and route edges with evidence, plus
unmatched-endpoint and unserved-call findings), M3 (solution front door and MCP)
and M4 (solution rules, enrichment and tours) are named in
`MULTI-REPO-DESIGN.md` and **none of them has a card in TASKS.md**. Only M1 does.

What that means today: a five-repo Supabase demo would render as five separate
maps behind an index page. It would not demonstrate the differentiator at all,
because the differentiator IS the edges between the repos. The owner is right
that multi-repo is extremely important. It is more unfinished than the plan
implied, and the missing part is the part that matters commercially.

One more detail for later: `--solution` does not clone git-URL members (out of
scope in M1, warns and skips). Our harness would hand it local clones anyway, so
this is not a blocker for us, but it is a gap for anyone else adopting it.

**Not a Wave 1 prerequisite.** VS Code, Kubernetes and Home Assistant Core are
each a single repository. Kubernetes only looks multi-repo; `staging/src/k8s.io/*`
lives inside the one repo and is correctly analyzed as one.

## 2. Java: the wall is much smaller than anyone documented

Wave 1 is TypeScript, Go and Python, all in the full-parse tier, so Java does not
gate the start either way. But the reason it does not is different from what the
program plan assumed, and the correction is worth more than the original point.

**The README's language table is stale.** It lists Java, Kotlin, C/C++, C# and
Dart as "detection + metrics only". In fact `analyzer/parsers/` contains
`java_ts.py`, `cpp_ts.py` and `csharp_ts.py`, the `treesitter` extra already
pulls `tree-sitter-java`, `tree-sitter-cpp` and `tree-sitter-c-sharp`, and all
three are registered in `PARSERS` with `_ts_available` true once the extra is
installed.

Probed against the repo's own `tests/fixtures/java` (2026-08-18), Java produced:

- **Symbols with kinds**: `record User`, `class UserService`, `class
  UserController`, methods `find`, `save`, `getUser`, `createUser`, fields
  `users`, `service`. Java records are recognised, so the grammar is current.
- **Framework detection**: the web component came back `framework: Spring`.
- **API endpoints**: `GET /users/{id}`, `POST /users`, `ANY /api`, extracted from
  the controller's annotations.
- **A relationship**: `web -> service (uses)`.

That is not "detection and metrics". That is the full-parse feature set on a
three-file fixture.

What this changes:

1. **Spring Boot may belong on Track A, not Track B.** The premise for putting it
   on the capability-forcing track was that a Java map would be blank. It will
   not be blank. Whether it is GOOD at forty-module, several-hundred-thousand-line
   scale is unproven and is exactly what the reconnaissance pass should measure.
2. **The 25 percent detect-only publishing gate needs recomputing** for any
   subject, because the set of detect-only languages is smaller than the README
   says.
3. **The README is wrong in a way that costs us commercially.** "No Java" is the
   kind of claim a buyer checks in the first five minutes, and we are currently
   telling them we cannot do something we can. Fixing the table is minutes of
   work and should happen with the next documentation pass.
4. **Kotlin and Dart remain genuinely unparsed**, and C/C++ and C# now need the
   same probe Java just had before anything is claimed either way.

One near-miss worth recording as method: the Java symbols came back with
`line_start: None`, which looked like a serious Java-specific defect until the
same check on Flask's Python symbols showed `line_start: None` for all 1,569 of
them. It is a property of that projection mode, not of the Java parser. Probing a
second language before filing is what stopped a false finding.

---

## 3. The prerequisites

### P1. Merge `wt/comprehension-fixes` (the big one)

Fifteen commits sitting unmerged and unpushed: all nine trust defects from the
cold-start study (S1 to S9), the aggregation rework, and double-tap snap zoom.
`main` is untouched at `e0c704e`.

Building demos on `main` today publishes, on someone else's famous codebase, the
exact defects the study found: cross-level edges silently dropped so the
client-to-server edge is invisible, confident misclassification ("Remote Log
Server"), a machine front door that contradicts the dataset, double-click drill
that does not drill, no rollup surface, no search relevance floor. That is the
single worst thing we could do to the shop window, and it is entirely within our
control to prevent.

The merge is a fast-forward (the branch was cut from main's tip) and the branch
is clean: tsc clean, eslint clean, viewer 381 passed with the 86 pre-existing
failures unchanged and the failing file set diffed identical, Python 1451 passed
with the 3 documented pre-existing failures.

It is not just a merge, though. Three attached steps:

1. **Golden corpus re-baseline.** The branch changes `derive/pipeline.py`,
   `derive/roles.py`, `extract/entities.py`, `parsers/base.py` and
   `project/frontdoor.py`. Projections will move, so `golden-corpus.py check`
   on Flask and FastAPI will report drift. That is the harness doing its job.
   Review the diff as an intended improvement, then approve the new baselines.
   Skipping this leaves a red regression gate that everyone learns to ignore.
2. **Redeploy the two UnaMentis installs**, so our existing public demos are not
   worse than the new ones. Note `um-arch.unamentis.org` is still pinned to a
   2026-03-06 SHA behind a comment that says `# main`, recorded in
   `DEPLOYMENTS.md` as owner action needed since July.
3. **Re-run the comprehension review on UnaMentis after the merge** (see P4).
   Same subject, before and after, which measures whether the nine fixes
   actually moved the number.

Effort: half a day to a day, plus the review.

### P2. Rescue the persona-run corpus. DONE 2026-08-18

The 2026-08-17 study's raw material was 28 MB sitting in a temporary session
scratchpad, and session scratchpads get cleaned up. It is the only calibration
data for the B+ baseline and the raw material the reproducible instrument is
derived from, so it was copied out before it could be lost. This was the one
action taken during this review; everything else here is analysis awaiting a
go-ahead.

Now at `/Volumes/Studio/dev/.evidence/solution-explorer/persona-runs/20260817`,
129 files, verified byte-identical to the source. Contents:

| Persona | Journal | Findings | Screenshots |
|---|---|---|---|
| p1 (Maya, senior engineer) | yes | yes | 47 |
| p2 (Doug, non-coding executive) | yes | yes | 31 |
| p3 (Priya, staff engineer, AI power user) | yes | **missing** | 46 |

Two things fall out of the inventory. The study report says "three findings
documents"; there are two. Priya's findings exist only inside her journal, so
the third persona's output was never separated the way the other two were. And
the screenshot count is 124, which matches the report exactly, so nothing else
was lost.

That missing document is itself an argument for the charter in section 4: a
run's required outputs have to be enumerated and checked, or the instrument
quietly produces different artifacts each time and the series stops being
comparable.

Still owed: a decision on where this lives permanently. It is outside the repo
right now, which keeps 28 MB of screenshots out of git history but leaves it
undiscoverable to anyone else. Options are a repo directory, git-lfs, or leaving
it local with a pointer committed. Not urgent, but it should not stay
undecided.

### P3. The `publication.json` publish gate

`PUBLICATION-METADATA.md` design rule 2 says the deploy paths "fail loudly when
`publication.json` is missing or invalid, and the error names the boilerplate to
copy". Verified: there are zero references to publication in `action.yml`,
`build.sh`, or the deploy and install commands, and no schema validator anywhere
in `analyzer/` or `scripts/`. The viewer half IS built and wired (`App.tsx` 462
and 956).

So today a demo can deploy with no showcase framing at all: no unofficial and
not-affiliated banner, no upstream license line, no snapshot provenance. For a
public map of a codebase we do not own, that banner is the entire legal and
ethical framing, and its absence would be silent.

Effort: half a day. A schema validator plus a gate in the deploy path plus a
test that the gate bites.

### P4. The comprehension review as a reproducible instrument

The owner's explicit ask, and the right one. Detail in section 4 below.

Effort: one to one and a half days to design and write the charter, rubric and
procedure. The first real run is the demo-1 work itself. The calibration run on
UnaMentis (P1 step 3) is another half day to a day.

### P5. License review and upstream LICENSE shipping

The license review that `DISCLOSURE-POLICY.md` has referenced since July does not
exist. And the viewer renders upstream README, CLAUDE.md and documentation
excerpts, so a deployed demo redistributes third-party copyrighted text, which
MIT, BSD and Apache-2.0 all permit and all require the notice to accompany.

Effort: half a day. A per-subject checklist, plus a harness step that copies the
upstream LICENSE into the bundle and a gate that fails without it.

### P6. Private-preview gating that is not theater

The owner wants demo 1 up but not public until confident. `DISCLOSURE-POLICY.md`
already specifies how: Cloudflare Access (email allowlist or one-time PIN) or a
passcode enforced server-side by a Pages Function, and it explicitly rules out
client-side-only gating as theater. That gate has to exist before demo 1
deploys, not after.

Effort: half a day, mostly Cloudflare configuration.

---

## 3.1 Scheduled but NOT prerequisites

| Item | Why it can wait | When |
|---|---|---|
| **Multi-repo M2, cross-repo edges** | No Wave 1 subject is multi-repo | Before Supabase. Card M2, M3, M4 now so they stop being invisible |
| **Java tier** | Wave 1 is TS, Go, Python, and Java turns out to be far more built than documented (section 2) | Probe C/C++ and C# the same way, then re-rate Spring Boot's track from the recon pass rather than from the README |
| **Blob read-before-size-check** | `_enumerate` calls `read_bytes()` before the `max_file_size` gate, so a large file is fully read into RAM regardless of the bound. VS Code peaked at 1.9 GB, which is fine. Kubernetes and Home Assistant are unmeasured | D0 measures it. Fix only if a subject actually blows up |
| **Classification accuracy instrument** | The comprehension review will find this class by hand first, and what it finds should define the automated checks | After demo 1, specified by demo 1's findings |
| **Retire `merge-ai-enhancements.py`** | Open and unowned since the Phase 7 gate | The demo program runs the enrichment path weekly on fresh datasets, which is exactly the parallel-run evidence that gate has been waiting for. Free byproduct, worth naming |

---

## 4. The comprehension review, made reproducible

Today it is a thing that happened once, brilliantly, and cannot be repeated
identically. To become an instrument it needs six things.

### 4.1 A versioned charter

`comprehension-review/v1`, capturing what the 2026-08-17 run did: three fixed
personas with fixed missions (a senior engineer who does not know the language
and must plan a real bug investigation; a non-coding executive who must produce
a stakeholder summary and do a mobile check; a staff engineer and AI power user
who must exercise every pathway including the machine endpoints and the export
loop); genuinely cold start, isolated port, cleared storage, no repo access, no
docs, a fixed time box; required outputs of a journal keyed to numbered
screenshots, a findings document, and a filled scorecard; and the orchestrator's
duty to independently verify every load-bearing claim, marking VERIFIED versus
CONFIRMED as the study already did.

### 4.2 A question battery, subject-agnostic plus a subject supplement

This is what makes runs comparable across different codebases. The fixed battery
asks the same things every time: what is this system in two sentences, what are
the three most important components and why, how does X talk to Y and over what
protocol, where does data live, what would you read first to investigate a
realistic bug, what is the biggest external dependency risk. The supplement is
generated per subject.

### 4.3 An answer key, which is the genuinely hard part

For UnaMentis the orchestrator could verify against source he could read. For VS
Code we need ground truth that is independent of the tool under test. Three
sources in priority order: the project's own architecture documentation and
published design notes; an independent agent reading the actual source with no
access to our projection; and for anything neither settles, mark the question
unscoreable for that subject rather than guessing. The key is built once per
subject and reused on every rerun, so the cost amortizes.

### 4.4 A rubric that produces numbers

"B+" is not comparable and not trackable. Score each persona on: time to a
correct one-paragraph description; question battery score against the key;
navigation efficiency against a defined optimum; trust incidents (count times
severity of things the tool stated that were false or unverifiable); recovery
(could the persona detect and correct a tool error unaided); and blocked paths
(advertised features that failed on first use). The demo's result is the set of
three persona scores, not their average, because the personas deliberately
measure different things.

### 4.5 Separating tool performance from subject difficulty

Record a difficulty profile per subject alongside the score: size, language mix,
share of lines in full-parse tiers, component count, documentation density,
external dependency count. Without it, a score drop just means the next subject
was harder, and the series is meaningless.

### 4.6 Improving the instrument without breaking the series

Every run ends with an instrument retro: which questions failed to discriminate,
which persona found nothing the other two did not, which defects a human caught
that the rubric missed. Changes bump the charter version. Results are comparable
within a version, and a version change requires re-running the previous subject
once to establish the offset. That is what makes "make it better every time"
safe instead of quietly drifting the scores.

### 4.7 Two practical notes

- **Reuse, do not duplicate.** The `gui-test-cycle` skill already has the harness
  conventions: one tab per shard with mandatory hygiene, evidence directories,
  `results.json` plus a blunt two-audience `REPORT.md`, a closed action
  vocabulary. The comprehension review is a different instrument (comprehension,
  not regression) but should borrow those conventions rather than invent a
  second set.
- **Cadence.** Three personas at 60 to 90 minutes each plus orchestrator
  verification is roughly half a day to a day of mostly unattended wall time.
  That is right for publication and for a major engine change. It is not right
  for the weekly refresh, which keeps the machine gates and the projection diff.
  Reading the owner's "every time we put one of these demos up" as publication
  rather than weekly.

---

## 5. Which demo first

The owner's instinct was hardest-first because it kicks more out of the bushes,
then he leaned the other way. The lean is correct, and the reason is stronger
than "it is easier".

**Recommendation: VS Code first, then Home Assistant, then Kubernetes, with a
reconnaissance pass over all three before any of it.**

### Why VS Code first

**Variable isolation.** Demo 1 is simultaneously the first run of five brand-new
things (registry, deploy path for a repo we do not own, hub, private-preview
gate, comprehension instrument) AND the first exposure of the analyzer to a
codebase nobody here has mapped. If the subject is also structurally exotic,
every failure is ambiguous: harness bug, analyzer gap, or subject weirdness. VS
Code's analyzer behaviour is already partly known from the Phase 4 benchmark
(16,482 files, 3.47M lines, 152 s cold, complete ledger), so a failure is far
more likely to be attributable to the new machinery.

**A pattern is established on the case where the pattern is the thing under
test.** Designing the pattern around one pathological subject usually produces a
harness that fits exactly one thing.

**Commercial.** Something defensible up early has value. Six weeks of wrestling
Kubernetes with nothing public does not.

The honest counter: VS Code yields fewer findings, and there is a real risk of
building a harness that quietly assumes a single language and a tidy structure,
then needs rework. Which is why:

### The reconnaissance pass

During D0, run analysis only on all three subjects. No enrichment, no deploy, no
fixing. The purpose is to see the shape of the Kubernetes and Home Assistant
problems early enough to design the harness knowing about them.

This does not violate the owner's "it would not make sense to find the same
error in three different places". Recon is not a fix cycle. We record what we
see and fix nothing until the demo whose turn it is.

### Why Home Assistant second and Kubernetes third

Home Assistant's difficulty is breadth: two thousand components, viewer scale,
search index size, enrichment cost. That is OUR presentation layer, which is
exactly what the last two campaigns rebuilt, so its fixes land in code we know
cold and compound immediately.

Kubernetes's difficulty is structural: symlinked staging modules, a vast
vendored tree, generated code. That is likely to need new analyzer concepts, and
it deserves a mature harness and a stable instrument so its findings are clean
signal rather than noise mixed with teething problems.

The trade, stated plainly: Kubernetes is the most commercially credible demo of
the three and this pushes it out by weeks. If that matters more than the clean
signal, swapping second and third costs little, because both come after the
pattern is set.

---

## 6. Realistic path to ready

| Step | Effort | Note |
|---|---|---|
| ~~P2 rescue the persona corpus~~ | done | Copied and verified 2026-08-18 |
| P1 merge the comprehension branch, re-baseline goldens, redeploy UnaMentis | 0.5 to 1 day | The largest single risk reduction available |
| P4 write the comprehension review charter and rubric | 1 to 1.5 days | Can run in parallel with P1 |
| Calibration run: comprehension review v1 on UnaMentis, post-merge | 0.5 to 1 day | Validates the instrument and the nine fixes at once |
| P3 publication gate, P5 license review, P6 private-preview gate | 1.5 days | Parallelizable |
| D0 pre-flight and the three-subject recon | 1 day | Ends with real numbers and the harness design settled |

About five to seven working days before demo 1 starts, assuming the calibration
run does not itself produce blocking findings. The honest note: this is not a
today job. P2 is minutes and P1 could be done today if the owner wants to move
now.
