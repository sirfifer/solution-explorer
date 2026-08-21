# The Enrichment Engine

Status: design of record for the permanent product. Written 2026-08-21 from the
owner's directives of 2026-08-20 and 2026-08-21; revised the same day to make
enrichment a climbed ladder with a per-item completeness contract, after owner
review. Supersedes the phase design in `ENRICHMENT-CALIBRATION.md` section 6.
Presentation copy: the "Enrichment Engine" artifact
(claude.ai/code/artifact/ac9c15dc).

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
   nothing checked truth. Section 4 turns this principle into a contract.
3. **Deterministic majority.** Everything derivable is derived, free, forever.
   Model spend goes only where mechanical work cannot reach.
4. **Iterative by nature.** The process must be able to loop. On the first
   Wave 1 subjects iteration is forced, with a genuine reasoned target each
   time, so the tuning that later decides "iterate or not" is learned.
5. **Fable finishes, always.** It may appear at the start, at the top of the
   ladder, and in the middle; the final determination is the appearance that is
   never optional.
6. **Every gap teaches the parser.** First question at every rung, no
   exceptions: how could deterministic processing have gotten this right, and
   how do we improve it so next time it does. Lessons phone home scrubbed under
   the license.
7. **Nothing regresses.** Isolation, validation on real work, rollback, and
   vetting against both the motivating code and random other parts before
   merge. Both golden corpora, every time.
8. **The ladder never redoes work that succeeded; it closes gaps that are
   named.** A higher tier receives the lower tier's attempt plus the specific
   failed question, never a blank assignment. This is the refined form of the
   earlier "higher tiers never rewrite" rule, which was too strong: rewriting
   success is waste, but writing what a lower tier could not write is the
   ladder's purpose.

## 2. The shape

```
P0   Deterministic foundation      (no AI)
P1   Orientation                   (FABLE)   what is this; the criteria
P2   The enrichment ladder
  2a   Bulk enrichment             (SONNET)  everything, weighted by importance
  2b   Escalated enrichment        (OPUS)    only items the contract failed
  2c   Residue enrichment          (FABLE)   only items two tiers could not ground
P3   Final adjudication            (OPUS)    verdicts and verification, writes nothing
P4   Synthesis                     (FABLE)   story spine, lenses, work orders
P5   Determination & accounting    (FABLE)   done or not; the Run Report
         |__ work orders descend to the ladder, bounded, and the run
             only exits through P5
```

An item climbs the ladder only when the completeness contract (section 4) says
it must, and each rung receives the previous attempt plus the named gap. The
ladder terminates: what Fable cannot ground becomes an honest, visible gap in
the product, never a faked answer and never an infinite loop. The P5
determination remains the only loop in the system.

Why this shape is also the cheap shape, measured 2026-08-20: enrichment cost
tracks the volume of OUTPUT, not context (~$10.5/M input tokens, ~$0.024 per
written component, ~$0.009 per written relationship). The base of the ladder
does the bulk writing on the cheapest tier; the upper rungs write narrowly by
construction, only the escalated items; the read-heavy phases (P1, P3, P4, P5)
write spines, verdicts and reports. Utility-first and efficiency-second want
the same architecture.

### How cost is denominated

Every model invocation, at every rung and phase, runs through the `claude` CLI
on **the owner's Claude Max subscription**. No API key is billed, and that
holds for **all** AI work in this engine until the owner deliberately changes
it (standing decision; the API-key invoker was declined 2026-08-18 and remains
declined). The dollar figures throughout this design are the API-equivalent
prices the CLI itself reports for the work performed. They are kept in dollars
deliberately, for three reasons: they are a truthful meter of how much
subscription usage a run consumes; they are the unit the `max_cost_usd`
ceilings meter against; and the design is expected to run on a billed API key
eventually, so when that switch happens, by decision rather than drift, every
projection, ceiling and Run Report ledger in this design already denominates
correctly. The design generalizes; the account it draws on today does not.

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
quality criteria, and any effort-weighting adjustments. The brief also warns
the ladder: a subject whose comments and code diverge, or whose naming carries
a non-native idiom, is declared up front so 2a knows confusion is expected and
escalation is cheap, not shameful. New phase.

**P2, the enrichment ladder.** One contract, three rungs, each applying the
same completeness contract to its own output.

- **2a, Sonnet, everything.** Semantic identification, untangling,
  human-language description across every component and relationship, weighted
  by the ranking. Every item exits in a contract state: `grounded`, or
  `escalate` with the failed questions named and the attempt attached. The
  calibration showed Sonnet is genuinely good at the base rung; the contract
  exists for the items where it is not.
- **2b, Opus, escalated items only.** For each: first adjudicate what Sonnet
  wrote (agree or correct, so nothing that succeeded is redone), then close the
  named gaps at its own level. Same contract, same exit states.
- **2c, Fable, the residue.** The items two tiers could not ground. Fable
  resolves them or declares an **honest gap**: a visible "this could not be
  established, and here is why" in the product itself, compliant with the
  no-theater rule. The ladder never fakes an answer to terminate.

Parser-first runs at every rung: each escalation asks first whether
deterministic processing could have prevented it. Exists: the
partition-and-invoke machinery for 2a; new: the contract fields, the escalation
plumbing, rungs 2b and 2c.

**P3, final adjudication (Opus, input-rate, near-zero output).** After the
ladder is quiet. The Phase 7 verify passes (edges, findings, identity: the S2
surface of name, type, framework, port), identity verdicts of agree / correct /
uncertain with reasons, plus grounding spot-checks over everything the ladder
wrote, whichever tier wrote it. Checking a citation is far cheaper than
producing one, so the asymmetry holds even for Fable's writes: the top of the
ladder does not escape verification. Rewrites nothing. Exists: the verify
passes and verdict overlay, currently never invoked; new: digests and wiring.

**P4, synthesis (Fable, read-everything, write-a-spine).** After adjudication,
because a story told over unverified labels narrates mistakes persuasively.
Writes the story spine as code-anchored **tours** (the viewer's tour player and
`Tour` contract are built, tested, advertised, and have never been fed), the
architecture narrative, and discovered **lenses**: the angle nothing else
caught, dug into just enough to confirm. A confirmed lens becomes a work order
executed by Opus or Sonnet. Federation is one level, capped, logged. Honest
gaps from 2c are material here, not embarrassment: "what even the deep read
could not settle" is part of an honest map's story.

**P5, determination and accounting (Fable, the verdict and the report).** Works
from the item census, the verdict census, the criteria, the story and the
lenses, not a re-walk of 570 components. Answers: good enough, or is there room
it knows how to close? "Not done" is only legal with work orders whose
instructions are designed to change the result, never "look again". Rounds
bounded and budget-aware. Always writes the Run Report.

**Forced iteration, early:** on the first Wave 1 subjects the determination
must run at least one improvement round even when it believes the map is done,
with a genuine reasoned target, never a checkbox. The report records cost and
measured plus perceived delta. Once rounds stop paying, learned criteria take
over; "no measurable gain from the forced round" is itself the finding that
earns the dial-back. Registry: `iteration.min_rounds`, at least 1 for Wave 1.

## 4. The completeness contract

The owner's challenge: make "is this item's enrichment complete" as
deterministic as possible, with guidelines every tier follows identically. The
answer has three parts: required questions, a grounding rule, and mechanical
escalation triggers. The design principle: convert as much of the judgment as
possible into checkable structure, and leave only sufficiency to adjudication.

### 4.1 The required questions, per component

1. **Purpose.** What is this for, in the subject's own terms?
2. **Mechanism.** How does it do it: the one or two structural facts a reader
   needs (the key types, the central flow)?
3. **Place.** What depends on it, what does it depend on, and why does that
   make sense?
4. **Identity.** Type, framework, port, language: each claim individually.
5. **Next step.** Where would a reader go from here, and why?

Relationships carry a reduced form (what flows, why it exists). The questions
are the same at every rung; only the intelligence applied to them changes.

### 4.2 The grounding rule

**A claim without evidence you can point at is not an answer.** Every answer
names its evidence: a file and line, a symbol, a manifest entry, a doc
passage, a relationship edge. An answer that cannot cite is either marked
`uncertain` with a reason or dropped; it is never left standing bare.

This rule is what makes the contract enforceable by code. A **no-AI evidence
validator** checks every citation mechanically: the file exists, the line is in
range, the named symbol appears there, the edge is in the graph. That validator
cannot judge whether the evidence *suffices*, but it makes unsupported claims
structurally detectable, which converts most of "is this real understanding"
from a vibe into a check.

### 4.3 Escalation triggers, mechanical

An item escalates when any of these hold, and the trigger travels with it:

| Trigger | Meaning |
|---|---|
| E1 no-answer | A required question the tier could not answer at all |
| E2 ungrounded | An answer whose evidence the tier could not cite (the grounding rule converts "I could not really tell" into this, structurally) |
| E3 contradiction | Evidence contradicts a deterministic fact or another claim; always also a parser-first finding |
| E4 substitution failure | The answer would fit a randomly chosen sibling component equally well; the tier self-applies the test, adjudication spot-checks it independently |
| E5 declared confusion | The tier states it cannot reconcile the code with its comments, docs or naming (the foreign-team case), with the specific confusion named |

The escalation record is: the attempt, the failed questions, the trigger, and
the evidence gathered so far. The next rung starts there, never from scratch.

### 4.4 Terminal states and the census

Every enrichment target ends the ladder in exactly one state:
`grounded@sonnet`, `grounded@opus`, `grounded@fable`, or `honest-gap`. The
census of these states is the backbone of the P5 determination and a first-class
section of the Run Report. A subject with 96% grounded at Sonnet and four
honest gaps is a different product, and a different story, from one with 60%
grounded at Sonnet, and the census is what lets P5 and the owner see which one
they have.

### 4.5 What honestly remains judgment

Whether cited evidence is *sufficient* for its claim is judgment, and the
contract does not pretend otherwise. It is handled three ways: adjudication
spot-checks grounded items (sampling weighted by importance), the
inter-tier disagreement rate on those spot-checks is a run metric, and that
metric feeds the learned tuning exactly as forced-iteration outcomes do. If the
disagreement rate is high, the contract's questions or the rung's instructions
need work, and the Run Report says so.

### 4.6 Moving down: the work order

One shape for P4 lens reviews and P5 improvement rounds alike: **scope**,
**lens**, **criteria**, **expected effect** (which instrument should move),
**budget**. Executed by Sonnet or Opus as an ordinary pass; results re-enter
through the same contract and the same adjudication they would have faced the
first time. One level of federation, capped, logged.

## 5. The Run Report

Every run ends with an artifact separate from the product: part invoice, part
bill of materials, part verdict with reasons. Machine JSON plus human
rendering, written even on partial failure.

| Section | Contents |
|---|---|
| identity | subject, exact commit, snapshot date, engine versions, policy |
| work ledger | per phase, rung and model: targets, tokens in/out, cost (API-equivalent dollars, metered against the owner's subscription; see section 2), wall, retries |
| item census | every target's terminal contract state, with failed questions and triggers for everything that climbed; the backbone of the determination |
| escalations | every item that climbed, the trigger, and what the higher rung did with it |
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
| Truth (verify verdicts + evidence validator + contract census) | claims vs their own evidence; S2; grounding | verify exists, never invoked; validator and census new; wired at P3 and counted in the gate |
| Utility (engagement proxies + comprehension review) | unprompted exploration, generated ideas, time to first orientation, drop-off; rubric per persona | review exists; proxies pilot against the 2026-08-19 persona material first |

## 7. Build order

Each step under the no-regression protocol: isolation, VS Code plus both
golden corpora, byte-identical output when the feature is off.

1. Phase seam in the engine: composable phases and rungs, a model per rung,
   work-order descent. Everything hangs off this.
2. Navigation-importance ranking, derive tier, no AI.
3. The completeness contract in the 2a payload: the questions, the grounding
   rule, contract states, triggers, plus the no-AI evidence validator.
4. The ladder: escalation plumbing, rungs 2b and 2c, the census.
5. P3 wiring: digests, identity verdicts, verify passes and grounding
   spot-checks into the run and the gate. Own small calibration first (5,086
   planned prompts on VS Code).
6. P1 orientation.
7. P4 synthesis: tours (additive overlay kind), narrative, lenses, work orders.
8. P5 determination, forced-iteration policy, the Run Report.
9. Persona review with engagement proxies; rinse and repeat.

Everything local until the map has been through reviews. Cloudflare, domains
and deploys are parked behind the graduation gate; nothing here depends on
them.
