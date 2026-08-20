# REVIEW: N1 calibration run, UnaMentis

Charter `comprehension-review/v1`. Subject: UnaMentis. Run date 2026-08-19.
Baseline: the 2026-08-17 sittings, scored retrospectively at
`docs/quality/runs/unamentis/2026-08-17/`.

## The result

```
unamentis -> unamentis (comprehension-review/v1)

P1 senior engineer, unfamiliar language   11/24 -> 17/24  (+6)
P2 non-coding executive                   12/24 -> 13/24  (+1)
P3 staff engineer, AI power user          6/24 -> 16/24  (+10)
    P3: model_accuracy not comparable (unscored on one side);
        P3's delta is a lower bound, not a measurement

Trust incidents: 17 -> 8
```

Reported as the set, never the average. The personas measure different things
and P2 is the one that barely moved.

**Read this as a floor, not a measurement.** Three things hold it down:

1. **The baseline is a floor.** P3's 2026-08-17 findings document did not
   survive, so its `model_accuracy` is null and its 6/24 understates whatever
   that sitting actually achieved. P3's +10 is the least trustworthy number
   here, and the scorer now says so on its own.
2. **The baseline scoring is ours.** The same orchestrator scored both sides.
   The compensating controls were to pre-register expectations before results
   existed (`PRE-REGISTRATION.md`) and to spot-verify the harshest baseline
   calls against the raw artifacts, both of which are recorded below.
3. **P2 moved by one point.** On the persona that matters most commercially,
   this run is close to no change.

## What actually improved, and what did not

**Trust improved materially and for identifiable reasons.** Incidents fell from
17 to 8, and more importantly they changed in kind. The baseline P1 wrote "I do
not believe it as stated" and the baseline P2 found a mislabelled component and
a 69-versus-265 endpoint contradiction. The 2026-08-19 P2 wrote "I did not catch
the tool stating anything I could actively disprove." Specific defects the
baseline hit were fixed.

**Snapshot freshness improved.** The baseline complained the data was 26 days
old. This run's data was 18 hours old.

**Run completeness improved.** All three personas produced all four required
outputs. The baseline run did not, which is what made it partially incomparable.

**Advertised paths did not improve at all.** P1 scored 2, P2 and P3 scored 0.
Every persona hit something that does not work. This is now the single largest
drag on the score, and it is a different problem from the trust defects that
were fixed.

**The executive case did not improve.** P2's two partial answers are the two
questions an executive asks first, and both trace to O1 below rather than to
anything the persona did.

## Independent verification

Convention retained from the 2026-08-17 study: **VERIFIED** means a root cause
was found, **CONFIRMED** means reproduced or corroborated only.

Full detail in `ORCHESTRATOR-FINDINGS.md`. Summary of the load-bearing checks:

| # | Claim | Status | Outcome |
|---|---|---|---|
| O1 | Documentation content is not searchable | VERIFIED | 233 of 233 markdown entries in the search index have empty text |
| O2 | "5 external dependencies" is a complete count | VERIFIED false | Hardcoded 18-domain dict; counts GitHub from a CI script, misses Unleash and LiveKit |
| O3 | Symbol search discards symbol targets | VERIFIED | `SearchOverlay.tsx:86-113` falls back to component navigation and never re-resolves |
| O4 | The UI advertises coverage it cannot deliver | VERIFIED | Badge renders "Coverage unavailable"; a "coverage ledger" is referenced and does not exist |
| O7 | P1's claim that the graph never rendered | VERIFIED FALSE | P1's own `31-root-view.png` shows the graph fully drawn |
| O8 | The tool asserts a contested port as fact | VERIFIED | `:8767` stated unhedged where the subject's own source disagrees with itself |
| P3 Fact B | 254 versus 251 component count | VERIFIED | Manifest 254 at 02:35:45Z, admin summary 251 at 02:38:43Z, same repo, same run |
| P3 Fact C | The changelog reports an id migration as real churn | VERIFIED | 253 of 254 added ids carry a `unamentis/` prefix; stripping it recovers 250 of 256 removed ids |
| P3 Q3.2 | `diff_summary` all zero across 20 commits | CONFIRMED, corrected | Component and relationship fields are zero; `files_changed` is not |

**Not independently reproduced**, and labelled as such in the cards rather than
quietly counted: P2's Inventory lens failing at 390x844, P3's Review mode
producing no visible change, and P3's "More options" menu never rendering.
These three remain open.

### Baseline calls I checked before accepting them

A harsh baseline flatters the improvement, so the harshest calls were checked
against the raw artifacts rather than accepted. P1's `trust: 0` rests on eight
distinct recorded trust issues and the persona's own refusal to believe a stated
figure. P2's `advertised_paths: 0` rests on four evidenced failures including a
summary banner that could only be restored by reloading the page. Both stand.

### Claims excluded from scoring after verification

- **P1's graph blocker.** Verified false (O7). Excluded from `advertised_paths`.
- **P2's lens-label blocker.** `LensSwitcher.tsx:47` is a native `<select>`, so
  an `<option>` is not independently clickable for an automation driver but is
  entirely usable by a person. Excluded as an automation artifact.

Both exclusions are recorded in the cards themselves so the exclusion is
auditable rather than invisible.

## The most consequential finding is not about comprehension

The changelog reports an id-namespace migration as 254 new component discoveries
and 256 removals, with every row reading "New component discovered". Roughly six
components genuinely changed. The other ~250 are the same components re-identified.

That matters far beyond this review. The demo programme's findings loop depends
on the weekly projection diff carrying signal, and this is the same class of
trap the programme has already been caught by once, recorded in the handoff as
"a bogus golden diff showing 989 phantom symbol losses". **N2 and N3 should not
rely on the projection diff until this is resolved.**

## Pre-registered expectations, resolved

Recorded in `PRE-REGISTRATION.md` before any findings document existed.

| | Expectation | Outcome |
|---|---|---|
| E1 | External dependencies under-answered, and it will be the map's fault | **FALSIFIED as stated.** P1 named ElevenLabs, Piper, Chatterbox and Ollama from the site alone, breaching the stated falsification criterion. What it revealed instead was sharper: the map's own two surfaces disagree, and P1 caught it |
| E2 | The coverage ledger is absent, not incomplete | **CONFIRMED**, and VERIFIED with a root cause (O4) |
| E3 | The single-laptop fact is either reached or unreachable | **Resolved on the negative branch.** Unreachable, and now root-caused to O1. Both executives missed it, a year of fixes apart, for the same structural reason |
| E4 | The 250/254 versus 251/251 enrichment discrepancy is a counting difference, not lost enrichment | **CONFIRMED.** The 251 is the admin pipeline's own component count, which is itself the subject of a verified disagreement |
| E5 | The baseline will be a floor | **CONFIRMED.** The scorer now says so unprompted |

Pre-registration earned its place: E1 was wrong, and having written it down in
advance is why that is visible rather than quietly reinterpreted.

## Instrument retro

### R1. The charter's own B+ mapping is wrong by about six points

The charter states "The old B+ maps to roughly 17 to 19 of 24." Scored against
the v1 rubric the same sittings yield 11, 12 and 6. The gap is conceptual, not
arithmetic: a holistic letter grade answers "could a non-expert understand this",
while the rubric also charges heavily for trust incidents and blocked paths. The
baseline P2 awarded B+ while listing eight blockers and writing "Directionally
yes, contractually no."

**Action: strike the 17-to-19 sentence from the charter.** The calibration run
has replaced it with real numbers, which is exactly what the charter said it
would do. This changes no score and needs no version bump.

### R2. Agent personas invent defects, and only screenshots catch it

P1 looked at a rendered graph, screenshotted it, and reported it did not exist.
No amount of rubric discipline catches that; only opening the evidence does.

**Actions.** Persona blocked-path claims are unverified by default and must be
checked against source or the persona's own screenshots before scoring. Add a
counter to the run record: claims checked, claims excluded. This run: 7 checked,
2 excluded.

### R3. The rubric has no slot for a persona inventing a defect

`unaided_recovery` scores whether a persona detected a *tool* error. There is no
dimension for the inverse, a persona asserting an error that does not exist,
which is arguably worse because it manufactures work. Candidate for v2.

### R4. Agent personas hit automation-only blockers

P2's lens-label failure is real for a Playwright driver and unreal for a human.
An instrument measuring human comprehension must not count it.

**Action.** Add to the charter's rules of engagement: a blocked path caused by
the persona's interaction modality rather than by the interface is excluded, and
the exclusion is recorded.

### R5. `compare` crashed on the exact case the charter mandates

`scripts/comprehension-score.py compare` raised `TypeError: '<' not supported
between instances of 'int' and 'NoneType'` when the baseline carried a null
dimension. Retrospective baselines are *required* to carry nulls. The prescribed
command could not run on the run it was designed for.

Fixed in this run: null on either side is now reported as not comparable, and
the affected persona's delta is labelled a lower bound rather than a
measurement.

### R6. The validator demands evidence for unscored dimensions, and misdescribes why

A null-score dimension still requires a non-empty `evidence` string, and the
error reads "has a score but no evidence". The requirement is defensible, since
explaining an absence is worth recording. The message is not. Cheap fix.

### R7. The profile's language-tier share was measuring the wrong thing

`PROFILE.json` initially recorded 8.78% of lines in full-parsing tiers. Restricted
to code, the figure is 96.72%. The full-parse line count is identical in both,
330,946; only the denominator changes, because full-parse languages never fall
outside the code class. The all-lines figure therefore measures how much bundled
data and documentation a subject carries, not how much of it the engine parses,
which makes it near-useless as a difficulty signal.

**Action.** Specify the profile field as code-only. Both figures are now recorded.
No score changes, so no version bump.

### R8. The answer key demanded an insight the tool cannot deliver

The key's P1 Q3 required linking the absent error message to the product's
deliberate fallback design. That design exists only in a markdown file, and
markdown content is unsearchable (O1). The key was written from the subject's
source without asking whether the tool exposes it.

**Action, and it generalises.** When building a key, mark each required fact
with whether the projection carries it. A fact the tool cannot surface is a
finding about the tool, not a scoring criterion for the persona. Recorded
against P1 Q3, which was scored `correct` on the reachable part.

### R9. P3's battery is about our tool, not about the subject

P3's five questions cannot be graded against subject ground truth the way P1's
and P2's can; they are verified instead. That asymmetry is inherent and probably
fine, but it means P3's `model_accuracy` measures "did this persona's claims
survive verification", a different quantity from P1's and P2's. It should be
named differently in v2, or P3 should get its own dimension set.

### R10. Which questions failed to discriminate

`orientation` scored 4 for all three personas, twice inside two minutes. The
product summary answers the orientation question immediately, so the dimension
no longer separates anything on this subject. Keep it, because a regression here
would matter, but expect no signal from it.

### R11. Staffing worked, and is now reusable

Isolation was established by construction rather than by instruction:
`scripts/comprehension-sitting.sh`. Verified profile: the persona has only
`ToolSearch`, `Write`, `TodoWrite` and the browser. It cannot read the
repository, cannot read the served mirror's raw files, cannot reach the
`unamentis` skill, and cannot search the web for the subject.

Three things were learned the hard way and are recorded in the script's header:
`--bare` breaks credential resolution; `--allowedTools` is an auto-approve list
and does **not** restrict availability, so a session with Bash "denied" still
ran `ls /`; and MCP tools need the server-level form `mcp__playwriter` to
survive alongside a deny list.

### R12. Serving the mirror faithfully mattered more than expected

The live origin answers every unmatched path with 200 and `index.html`. A plain
static server 404s. P3 chased four advertised `/architecture/*.json` URLs and
recorded the 200-with-HTML behaviour, which is real. Had the mirror been served
naively, that finding would have been a mirror artifact instead.

## Charter version

No version bump. Every change identified here is either a documentation
correction (R1, R7), a tooling fix (R5, R6), or a candidate for v2 (R3, R4, R9).
None alters how a score is computed, so the series remains comparable and no
re-run of a previous subject is owed.

## What remains open

1. Three persona claims not independently reproduced (P2 mobile Inventory lens;
   P3 Review mode; P3 "More options" menu).
2. Whether the 254-versus-251 disagreement originates in our live-architecture
   pipeline or in the subject's CI. The viewer consumes it at
   `viewer/src/hooks/useAdminData.ts:31`; the producer was not traced.
3. Whether the "5 external dependencies" label should be redefined or the
   detection completed. O2 establishes it is not a deliberate definition.
