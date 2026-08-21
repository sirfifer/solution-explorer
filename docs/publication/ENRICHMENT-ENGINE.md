# The Enrichment Engine

Status: design of record for the permanent product, written 2026-08-21 from the
owner's directives of 2026-08-20 and 2026-08-21. Supersedes the phase design in
`ENRICHMENT-CALIBRATION.md` section 6. Presentation copy for review:
the "Enrichment Engine" artifact (claude.ai/code/artifact/ac9c15dc).

This is not scaffolding for one run. It is how every subject SysCorpus ever
maps goes from deterministic fact to something a person is drawn into, and how
the process knows it is actually done rather than merely finished.

## 1. The mandate

1. **Utility above all.** Quality, richness, accuracy, and above everything the
   ability of a person to genuinely understand and navigate the model. Token
   efficiency is a high priority and strictly second: efficiency buys the
   headroom to be uncompromising, it does not make the process cheap.
2. **Completeness is not a checkbox.** The standard is "did you actually learn
   something", never "every field is filled". Measured proof of the difference:
   83 of 99 calibration components scored exactly 85.0 on the form scorer while
   nothing checked truth.
3. **Deterministic majority.** Everything derivable is derived, free, forever.
   Model spend goes only where mechanical work cannot reach.
4. **Iterative by nature.** The process must be able to loop. On the first
   Wave 1 subjects iteration is forced, with a genuine reasoned target each
   time, so the tuning that later decides "iterate or not" is learned.
5. **Fable finishes, always.** It may also appear at the start and middle; the
   final determination is the appearance that is never optional.
6. **Every gap teaches the parser.** First question, no exceptions: how could
   deterministic processing have gotten this right, and how do we improve it so
   next time it does. Lessons phone home scrubbed under the license.
7. **Nothing regresses.** Isolation, validation on real work, rollback, and
   vetting against both the motivating code and random other parts before
   merge. Both golden corpora, every time.

## 2. The shape

```
P0  Deterministic foundation        (no AI)
P1  Orientation                     (FABLE)   what is this; the criteria
P2  Bulk enrichment                 (SONNET)  the big spend, output-heavy
P3  Adjudication                    (OPUS)    verdicts, near-zero output
P4  Synthesis                       (FABLE)   story spine, lenses, work orders
P5  Determination & accounting      (FABLE)   done or not; the Run Report
        |__ work orders descend to P2/P3, bounded, and the run
            only exits through P5
```

Why this shape is also the cheap shape, measured 2026-08-20: enrichment cost
tracks the volume of OUTPUT, not context (~$10.5/M input tokens, ~$0.024 per
written component, ~$0.009 per written relationship; one partition took 17x
less input than another and cost half as much). So the most capable model
reading everything and writing a spine, verdicts and a report is the cheapest
possible use of it. Utility-first and efficiency-second want the same
architecture.

## 3. The phases

**P0, deterministic foundation.** Structure, symbols, metrics, relationships,
coverage, full-history activity, plus one new derivation: the
**navigation-importance ranking** from activity hotspots, relationship fan-in
and entry points. `frontdoor.py` already advertises exactly this recipe to
machine readers; nothing computes it. It becomes the effort-weighting input for
every phase above. Exists: nearly all; the ranking is new, derive-tier, no AI.

**P1, orientation (Fable, read-heavy, tiny output).** Reads README, docs, the
deterministic summary and the ranking. Writes the **subject brief**: what this
thing is, who will read the map, what would matter to them, subject-specific
quality criteria, and any effort-weighting adjustments. This is where the
determination gets its teeth: criteria are authored per subject, up front, by
the tier that will later enforce them. New phase.

**P2, bulk enrichment (Sonnet, output-heavy, the big spend).** Semantic
identification, untangling, human-language description across every component,
weighted by the ranking. Two mandatory payload additions: self-declared
`uncertain` with a written reason on anything unsettled, and the parser-first
finding for anything found missing, wrong or thin, filed to the findings loop
as a capability card. Never trusted alone; identity claims are adjudicated
above. Exists: the partition-and-invoke machinery; new: weighting and the two
fields.

**P3, adjudication (Opus, input-rate, near-zero output).** Reads compact
digests (label plus evidence pointer, never full prose), rewrites nothing.
Emits agree / correct / uncertain with reasons over the S2 surface (name, type,
framework, port). Runs the Phase 7 verify passes, which exist today and are
never invoked by anything. Escalation into P3 is mechanical: importance band,
declared uncertainty, verdicts, or a work order. Routing is never the expensive
tier's job.

**P4, synthesis (Fable, read-everything, write-a-spine).** After adjudication,
because a story told over unverified labels narrates mistakes persuasively.
Writes the story spine as code-anchored **tours** (the viewer's tour player and
`Tour` contract are built, tested, advertised, and have never been fed), the
architecture narrative, and discovered **lenses**: the angle nothing else
caught, dug into just enough to confirm. A confirmed lens becomes a work order
executed by Opus or Sonnet. Federation is one level, capped, logged.

**P5, determination and accounting (Fable, the verdict and the report).** Works
from the ranking, verdict census, criteria, story and lenses, not a re-walk of
570 components. Answers: good enough, or is there room it knows how to close?
"Not done" is only legal with work orders whose instructions are designed to
change the result, never "look again". Rounds bounded and budget-aware. Always
writes the Run Report.

**Forced iteration, early:** on the first Wave 1 subjects the determination
must run at least one improvement round even when it believes the map is done,
with a genuine reasoned target, never a checkbox. The report records cost and
measured plus perceived delta. Once rounds stop paying, learned criteria take
over; "no measurable gain from the forced round" is itself the finding that
earns the dial-back. Registry: `iteration.min_rounds`, at least 1 for Wave 1.

## 4. Moving up, moving down

**Up (mechanical, never a judgment call):** top importance band; lower tier
declared `uncertain` with its reason travelling along; adjudication said
`correct` or `uncertain`; or a work order names the target. Form scorer is a
sanity floor only.

**Down (one shape for P4 lenses and P5 rounds):** scope, lens, criteria,
expected effect (which instrument should move), budget. Executed as an ordinary
Sonnet/Opus pass; results re-enter through the same adjudication. One level of
federation, capped, logged.

## 5. The Run Report

Every run ends with an artifact separate from the product: part invoice, part
bill of materials, part verdict with reasons. Machine JSON plus human
rendering, written even on partial failure.

| Section | Contents |
|---|---|
| identity | subject, exact commit, snapshot date, engine versions, policy |
| work ledger | per phase and model: targets, tokens in/out, cost, wall, retries |
| escalations | every target that moved up, the signal, and the outcome |
| work orders | issuer, scope, lens, criteria, budget, outcome |
| iterations | forced or determined, reasoned target, measured delta AND perceived delta (labelled as judgment); a no-gain round recorded as exactly that |
| parser findings | every parser-first answer filed, as capability cards |
| criteria | the P1 brief's criteria plus universal gates, each with verdict and evidence |
| determination | done or not, with Fable's reasoning in full |
| lessons | scrub-safe abstractions for the licensed phone-home |

## 6. Three instruments, one claim discipline

Any claim a change "worked" must name which instrument moved.

| Instrument | Measures | State |
|---|---|---|
| Form (completeness scorer) | fields, shape, enums | exists; demoted to sanity floor |
| Truth (verify verdicts) | claim vs its own evidence; S2 | exists, never invoked; wired at P3, counted in the gate |
| Utility (engagement proxies + comprehension review) | unprompted exploration, generated ideas, time to first orientation, drop-off; rubric per persona | review exists; proxies pilot against the 2026-08-19 persona material first |

## 7. Build order

Each step under the no-regression protocol: isolation, VS Code plus both
golden corpora, byte-identical output when the feature is off.

1. Phase seam in the engine: composable phases, model per phase, work-order
   descent. Everything hangs off this.
2. Navigation-importance ranking, derive tier, no AI.
3. P2 payload additions (uncertainty, parser-first), findings-loop wiring.
4. P3 wiring: digests, adjudication, verify passes into run and gate. Own
   small calibration first (5,086 planned prompts on VS Code).
5. P1 orientation.
6. P4 synthesis: tours (additive overlay kind), narrative, lenses, work orders.
7. P5 determination, forced-iteration policy, the Run Report.
8. Persona review with engagement proxies; rinse and repeat.

Everything local until the map has been through reviews. Cloudflare, domains
and deploys are parked behind the graduation gate; nothing here depends on
them.
