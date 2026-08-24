# Incorporating the Enrichment Engine into the existing tech

Status: plan of record, written 2026-08-22 after PR #105 landed the engine.
Owner directive: *"incorporate to the best that we can this new material into our
existing tech before we do the first new demo."*

The design of record is `ENRICHMENT-ENGINE.md`. The build plan, all executed, is
`ENRICHMENT-ENGINE-BUILD.md`. This document answers a different question from
both of them: **the engine works, but does anything the engine produces actually
reach a person?**

## 1. The test this document applies

A capability is not incorporated because it exists. It is incorporated when it
survives the whole path from the store to a human being looking at the map:

```
ladder writes -> store row -> projection overlay -> published bundle
              -> viewer renders -> a person sees it
              -> and a gate would notice if it stopped arriving
```

Every finding below is a break in that chain, and each one was **verified
empirically or by reading the code**, not inferred. Where a defect predates this
work, it says so; the point is what has to be true before demo one, not who
caused it.

## 2. What actually reaches a person today

| Capability | Written | In the store | In the bundle | Rendered | Gated |
|---|---|---|---|---|---|
| `ai_enhance` blocks | yes | yes | **no, see I1** | yes, if it arrived | partly |
| Tours | yes | yes | **no, see I1 and I3** | yes, player exists | no |
| Honest gaps | yes | yes | **no, see I1** | **NO, see I2** | no |
| Contract census | yes | yes | by design, no | Run Report only | yes, demo-site |
| Importance ranking | yes | yes | by design, no | no | no |
| Adjudication verdicts | yes | yes | no | Run Report only | yes, demo-site |
| Parser findings | yes | Run Report | no | no | no |

Two of those rows are the difference between a demo and an embarrassment.

## 3. The findings

### I1. The harness never re-projects after enhancing, so it would publish an unenriched map. BLOCKER.

**This is the most important finding in this document, and it predates the
Enrichment Engine.** It came in with the harness itself (PR #103) and affects the
old bulk path exactly as much as the ladder.

`scripts/demo-site.py`'s `refresh` sequence is:

```
fetch -> analyze -> enhance -> validate -> diff -> deploy
```

`run_analyze` projects the bundle from the store. `run_enhance` then writes
enrichment rows **into the store**. Nothing re-projects. The bundle that gets
validated and deployed was built before any enrichment existed.

Verified empirically on the polyglot fixture, projecting before and after
stamping an enrichment row, a tour and an honest gap:

```
Bundle the harness would actually DEPLOY (projected before enhance):
  ai_enhance components=0   tours=0   honest_gaps=no
Bundle if it re-projected after enhance:
  ai_enhance components=1   tours=1   honest_gaps=yes
```

**Every gate would have agreed the bundle was fine.** `enrichment_quality` reads
the enhance report, not the bundle. `front_door_agrees` compares `ai.json`'s
enrichment claim against the manifest, and both would consistently say "not
enriched". This is precisely the cross-surface agreement failure the handoff
names as the signature of two of the deepest defects found so far: every surface
passing its own check while the thing as a whole is wrong.

**Fix:** `refresh` re-projects after `enhance` and before `validate`. The
standalone `enhance` subcommand prints that the bundle is now stale and names the
command to refresh it. Add a gate that reads the BUNDLE and fails when the store
has enrichment rows the manifest does not carry, so this class cannot return
silently.

Effort: **S** for the re-project, **S** for the gate. Both are half-day items.

### I2. Honest gaps are invisible in the product. BLOCKER for the honesty promise.

`grep -rn "honest_gaps" viewer/src` returns nothing. The ladder can declare "this
could not be established, and here is why", it rides in
`component.ai_enhance.honest_gaps`, it reaches the manifest as a passthrough, and
the viewer renders **nothing**.

That is not a cosmetic gap. The no-theater rule is the reason the ladder
terminates in an honest gap rather than a faked answer, and right now the product
converts an honest gap into a silence, which is the failure mode the whole design
exists to prevent. A reader cannot tell "we checked and could not establish this"
from "nobody looked".

**Fix:** render honest gaps in the existing **AI Insights** tab
(`DetailPanel.tsx` already gates that tab on `component.ai_enhance`), plus a
quiet marker on the component card so a reader can see there is a declared gap
without opening the panel. Copy matters here: it is a statement of what was
checked and not established, not an apology.

Effort: **M**. One viewer card plus tests. Needs a design decision on the marker
(section 5, D1).

### I3. `merge-ai-enhancements.py` drops tours on the GitHub Action path.

`merge()` copies `ai_enhance` at the component, relationship and root levels
(`scripts/merge-ai-enhancements.py:228-299`) and nothing else. `action.yml` uses
it to restore enrichment onto a fresh analysis. Top-level `tours` is not carried,
so a push-triggered re-analysis silently loses every tour.

This does not affect the demo harness once I1 is fixed, because the harness
re-projects from the store, which is the authority. It does affect the dogfood
and any installed repo using the Action.

**Fix:** carry top-level `tours` in `merge()`, and make the key list explicit and
tested so the next top-level enrichment key does not have to be discovered the
same way.

Effort: **S**.

### I4. The publish gate knows nothing about the new surfaces.

`scripts/validate-publication.py` has no mention of tours, honest gaps or the
census. A bundle can publish with a tour whose step points at a component that no
longer exists, or an honest gap with an empty reason, and nothing objects.

**Fix:** three checks. Every tour step's `target` resolves to a component in the
same bundle. Every honest gap carries a non-empty `why`. A bundle whose store ran
the ladder carries a Run Report alongside it. Keep the NOT_IMPLEMENTED
discipline: a check whose input is absent says so loudly.

Effort: **S to M**.

### I5. The ritual does not know the ladder exists.

`.claude/skills/ai-assist/SKILL.md` is the actual product ritual, the thing a
person or an agent follows to enhance and deploy. It documents `analyze.py
enhance` and never mentions `--ladder`, the Run Report, or the re-projection step
that I1 makes mandatory.

Notably the skill DOES already document "Step 3: Re-project so the viewer data
carries the enhancement". The ritual has the step; the harness does not. That is
worth recording: the automation regressed against its own written procedure.

**Fix:** update the skill with the ladder path, when to prefer it, what the Run
Report is, and the re-projection step made explicit.

Effort: **S**.

### I6. The front door does not advertise honest gaps or the Run Report.

`analyzer/project/frontdoor.py` already advertises tours (line 67), which is why
tours needed no front-door work. It says nothing about honest gaps, so a machine
reader has no way to learn that the map declares what it could not establish.

**Fix:** add honest gaps to the advertised surface. Consider advertising the Run
Report's existence for a ladder-enriched bundle.

Effort: **S**.

## 4. The order of work

Sequenced so that each step is verifiable and nothing depends on an owner
decision that has not been made.

**Before demo one, non-negotiable:**

1. **I1**, re-project after enhance, plus the bundle-versus-store gate. Without
   this, demo one publishes an unenriched map and every gate approves it.
2. **I2**, honest gaps rendered. Without this, the map's central honesty claim is
   dark, and a comprehension review would be reviewing a product that hides its
   own gaps.
3. **I4**, publish-gate checks. Cheap, and it is what stops I1 and I2 from
   regressing quietly.

**Before demo one, strongly preferred:**

4. **I3**, tours survive the Action path.
5. **I5**, the ritual documents the ladder and the re-projection.
6. **I6**, the front door advertises honest gaps.

**After the first real run, not before:**

7. Whether `--ladder` becomes the default (section 5, D2). That decision needs
   evidence from a real run, and there is none yet.

Total for items 1 to 6: roughly **two to three days**, most of it in I2 and I4.

## 5. Decisions for the owner

Per the working agreement, each carries options, a recommendation, and what it
would cost.

### D1. How should an honest gap look to a reader?

The content is settled: the question that could not be answered, and why. What is
not settled is prominence.

| Option | For | Against | Effort |
|---|---|---|---|
| **A. AI Insights tab only** | Invisible unless a reader is already digging. No risk of the map looking full of holes | A gap nobody opens the panel to find is barely more visible than no gap at all | S |
| **B. Tab plus a quiet marker on the card (RECOMMENDED)** | A reader can see a declared gap exists without hunting, and the detail is one click away. Honest without being alarming | Slightly more viewer work; needs restrained visual design | M |
| **C. Tab, card marker, and a map-level "what this map does not know" summary** | Strongest honesty story, and genuinely useful to an evaluator | Risks foregrounding gaps over content on a first impression, which is the opposite of a shop window | L |

**Recommendation: B**, with C revisited after the first comprehension review on a
real subject. C is the right long-term answer if the review shows evaluators want
it, and guessing now is exactly the "hard to establish, wait for more data" case
the deferred-work rule covers.

### D2. Does `--ladder` become the default?

Not yet, and not on a guess. It should become the default only after a real run
shows the census, the cost and the disagreement rate on a real subject. Recorded
here so it is a decision rather than a drift.

### D3. Do the two live UnaMentis demos get re-enriched with the ladder?

They currently carry old-engine output. Re-enriching them would make them
consistent with the new standard and would be a second data point before Wave 1.
It also spends subscription usage on already-published maps.

**Recommendation: no, not before demo one.** VS Code is the subject that matters
and the usage is better spent there. Revisit at the Wave 1 retrospective.

## 6. What this does not cover

- The first real ladder run itself. Owner-gated; the command is in PR #105.
- Anything Cloudflare, domains, DNS or deploys. Parked.
- The findings-to-issues filer (`DEMO-PROGRAM.md` 5.2), which is its own track.
- Surfacing the importance ranking in the projection, which would move both
  golden baselines and needs its own approval.
