# Comprehension Review

Charter version: `comprehension-review/v1`. Adopted 2026-08-18, derived from the
cold-start study of 2026-08-17 (`docs/remediation/COMPREHENSION-STUDY-2026-08-17.md`).

## What this is

The one instrument that measures the claim at the centre of VISION.md:

> A person in technology who does not know the codebase or even the language
> must navigate efficiently, figure out how it works, and start finding issues
> with no AI required.

Three personas run genuinely cold against a deployed site, answer a fixed
battery of questions, and are scored against an independently built answer key.
It ran once, by hand, produced nine findings and a B+ from all three personas,
and could not be repeated identically. This charter makes it repeatable,
comparable across subjects, and improvable without silently drifting the scores.

**It runs on publication and on a major engine change, not on the weekly
refresh.** Three personas plus verification is half a day to a day of mostly
unattended time. The weekly refresh keeps the machine gates and the projection
diff; this is what gates a demo going public.

## Rules of engagement

1. **Genuinely cold.** No persona reads the repository, the docs, this charter,
   or another persona's output. They experience only what the site offers.
2. **Isolated.** One port per persona, storage cleared before the run, one
   browser tab for the sitting (the `gui-test-cycle` tab-hygiene rule).
3. **Time-boxed.** 60 to 90 minutes each. The box is part of the measurement:
   the claim is about one sitting.
4. **Everything claimed is screenshotted.** A journal entry that cites no
   screenshot is not evidence.
5. **The orchestrator verifies independently.** Every load-bearing claim is
   checked against the dataset and the source. The study's convention holds:
   VERIFIED means a root cause was found, CONFIRMED means reproduced or
   corroborated.
6. **Nothing is softened.** A defect the personas hit is recorded at the
   severity they hit it, whatever it costs us.

## Required outputs, enumerated

Enumerated because the first run did not produce them uniformly: two of the
three personas wrote a findings document and the third's findings survived only
inside their journal, which makes that run partially incomparable with the next
one. A run is not complete until every persona has produced all four.

| Output | Contents |
|---|---|
| `JOURNAL.md` | Narrative, in order, every section naming the screenshots it rests on |
| `FINDINGS.md` | Mental model; answers to the battery with confidence and source; ranked confusions and blockers; moments of delight; trust assessment; verdict |
| `SCORECARD.json` | The rubric below, scored, with one evidence pointer per dimension |
| `evidence/` | Numbered screenshots, referenced by number from the journal |

The orchestrator adds `REVIEW.md` (verification of every load-bearing claim, the
combined defect list, and the instrument retro) and `PROFILE.json` (the
subject-difficulty profile).

## The three personas

Fixed roles, because comparability requires the same instrument each time. Each
carries a mission and a five-question battery.

### P1: the senior engineer who does not know the language

A senior backend engineer, fluent in their own stack, with no experience of the
subject's primary language. Mission: understand the system well enough to plan a
first bug investigation.

1. What is this product, for whom, and what are its moving parts?
2. How does the primary client talk to its backend, over what protocols and ports?
3. Given a realistic symptom (chosen per subject from the subject's own domain),
   where do you look first, in order?
4. Where does data live, and what does the system depend on externally?
5. Could you sketch this architecture on a whiteboard afterwards?

### P2: the non-coding executive

A technology executive who last wrote code fifteen years ago. Mission:
stakeholder comprehension and a founder-ready summary. Includes a mobile
hallway check at 390x844.

1. What does this system do, in language you would use with a board?
2. What is critical, and what happens if it fails?
3. What does this depend on that we do not control?
4. Where is the risk concentrated?
5. Could you brief someone from this in five minutes?

### P3: the staff engineer and AI power user

A staff engineer who drives tools hard. Mission: exercise every pathway,
including the machine front door, deep links, search, and the review-and-export
loop, and check consistency across them.

1. Does every pathway to the same fact agree (UI, search, `ai.json`, `llms.txt`,
   deep links)?
2. Can an agent answer a real question from the machine front door alone, and at
   what token cost against reading the raw repository?
3. What does the tool claim that it cannot support?
4. What is the fastest route from a question to a precise, citable answer?
5. Would you trust its output in a code review?

## The answer key

The hardest part, and the one that decides whether a score means anything. The
key is built ONCE per subject and reused on every rerun, so the cost amortizes.

Sources, in priority order:

1. **The project's own architecture documentation** and published design notes.
2. **An independent agent reading the actual source**, with no access to our
   projection. This is the expensive source and the honest one.
3. **Neither settles it: mark the question unscoreable for this subject** and
   record why. Never guess a key. A wrong key is worse than a missing one,
   because it turns a correct answer into a recorded failure.

The key states, per question: the expected answer, the facts that must appear,
the facts that would be wrong, and its own source. For the UnaMentis subject the
key can be reconstructed from the 2026-08-17 study's verification section.

## The rubric

Six dimensions per persona, each 0 to 4 against explicit anchors. A persona
scores out of 24. **The result of a run is the set of three persona scores, never
their average**, because the personas deliberately measure different things and
an average hides the one that failed.

| Dimension | 0 | 2 | 4 |
|---|---|---|---|
| **Orientation** | Never reaches a correct one-paragraph description | Correct description inside the time box | Correct description inside five minutes |
| **Model accuracy** | Under half the battery correct against the key | Most correct, with material gaps | Every scoreable question correct, gaps stated as gaps |
| **Navigation efficiency** | Could not reach named targets | Reached them, well over the defined optimum | At or near the optimum path |
| **Trust incidents** | Repeated false statements, verify-everything mode | Some, recovered | None encountered |
| **Unaided recovery** | Believed a tool error and built on it | Suspected it, could not resolve it | Detected and corrected it using the tool alone |
| **Advertised paths** | A taught gesture failed on first use | Worked after a retry or a workaround | Everything advertised worked first time |

Two things are counted, not scored, and reported alongside:

- **Trust incidents**: each thing the tool stated that was false or
  unverifiable, with severity. These become findings regardless of the score.
- **Blocked paths**: each advertised feature that failed on first use.

The old B+ maps to roughly 17 to 19 of 24. It is recorded as the v1 baseline for
UnaMentis, and the calibration run replaces it with a real number.

## Separating tool performance from subject difficulty

Without this, a score drop just means the next subject was harder, and the
series is meaningless. `PROFILE.json` records, per subject and per run:

size in files and lines; language mix and the share of lines in full-parse
tiers; component count and maximum drill depth; documentation density (doc lines
per code line); external dependency count; enrichment coverage; whether the
coverage ledger is complete; and the fit zoom the level renders at on each of
the three reference viewports.

A score is only ever compared against another score with a similar profile, or
with the profile difference stated explicitly.

## Improving the instrument without breaking the series

Every run ends with an **instrument retro** in `REVIEW.md`:

- Which questions failed to discriminate (everyone scored the same)?
- Which persona found nothing the other two did not?
- What did a human notice that the rubric had no slot for?
- Which key entries turned out to be wrong or unscoreable?

Changes are made deliberately and bump the charter version. The rules:

1. Results are comparable **within** a charter version.
2. A version change requires **re-running the previous subject once** on the new
   version, to establish the offset between them. Without that, an improvement
   to the instrument is indistinguishable from a regression in the product.
3. The charter version is recorded in every `SCORECARD.json` and `REVIEW.md`.

## Relationship to the other instruments

- **`gui-test-cycle`** is regression: does the UI still do what it did? It owns
  the harness conventions this borrows (one tab per shard, evidence directories,
  a machine-readable result plus a blunt two-audience report, a closed action
  vocabulary). Comprehension is a different question and does not replace it.
- **Machine gates and the projection diff** run on every weekly refresh and are
  cheap. This is the expensive instrument that gates publication.
- **The classification accuracy audit** (`DEMO-PROGRAM.md` section 5.3) does not
  exist yet and should be specified from what this review finds by hand on the
  first demo, rather than guessed at now.

## Where a run lives

`docs/quality/runs/<subject>/<date>/` for the orchestrator outputs, with the raw
persona material kept out of git for size and pointed at from the run record.
The 2026-08-17 baseline material is at
`/Volumes/Studio/dev/.evidence/solution-explorer/persona-runs/20260817/`
(3 journals, 2 findings documents, 124 screenshots), rescued from a temporary
scratchpad on 2026-08-18.
