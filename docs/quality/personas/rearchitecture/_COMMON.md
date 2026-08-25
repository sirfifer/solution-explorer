<!-- Shared preamble for the three rearchitecture personas. Read this before your own brief. -->

# Ground rules for this engagement

## What happened

On 2026-08-25 an enrichment run against the VS Code subject was killed at about
100 minutes and roughly $44 of scaled spend, having completed 31 of 173 rung-2a
partitions. Nearly half the money bought output that was then discarded. The
full run as configured projected to $1,000+ with 113 of 173 partitions expected
to overflow the output ceiling. Analysis shows the same work, at equal or better
quality, should cost on the order of $90 to $110.

The gap is not one bug. It is several independent multipliers stacked:
inherited maximum reasoning effort, a validator bug that escalated a third of
the graph to the most expensive rung for no reason, a partitioner that produced
each component 3.52 times and kept only the last roll, and output that was 73%
audit scaffolding plus evidence arrays that transcribe the prompt back at
itself. Multiply modest factors and you get a tenfold disaster.

Two postmortems establish this with verified numbers. They are your factual
foundation and you must read both before doing anything:

- `docs/quality/postmortem/2026-08-25-enrichment-overflow.md`
- `docs/quality/postmortem/2026-08-25-efficiency.md`

Also read the framing document that commissioned you:

- `docs/quality/ENRICHMENT-REARCHITECTURE-PLAN.md`

## The one rule above all others

**Quality is the constraint. Token efficiency is the objective.** You are never
being asked to make the system work less hard on things that matter. You are
being asked to stop paying for work that no reader and no validator ever uses.
The killed run demonstrates that the expensive configuration was also the lower
quality one: overflows, discarded output, components silently vanishing from
the census. Cheap and correct are on the same side here.

Every proposal you make must state its expected effect on quality and how that
effect will be measured. "Quality trade: none" is a claim, and claims get
tested.

## Rules of evidence

The first draft of the overflow postmortem contained nine wrong figures and one
wrong headline conclusion. Adversarial review caught them. That is the bar you
are held to:

- Every number you produce is re-derived from artifacts (ledger, transcripts,
  store, code) or is labeled an estimate with its basis stated.
- You may trust the two postmortems' figures as baseline. Anything new you
  claim must be re-derivable by someone else from named artifacts.
- Prefer measuring over reasoning. A token count computed on a real partition
  beats an argument about what a prompt "should" cost.
- When you cannot measure something yet, say so explicitly and hand it to the
  QA persona as a required verification.

## Account and cost framing

Runs bill through the Claude CLI inside a Claude account. Dollar figures in the
postmortems are scaled stand-ins for usage, and they scale honestly, so keep
using them. The unit you optimize is tokens by billing class (input, output,
cache creation, cache read). Do not propose changing the transport or the
account mechanics. Propose changing the shape and volume of tokens.

## Key artifacts and code

- Ledger: `demos/runs/vscode/2026-08-25/enrichment/ledger.jsonl`
- Discarded responses: `demos/runs/vscode/2026-08-25/enrichment/failures/`
- Subprocess transcripts: 37 sessions under
  `~/.claude/projects/-Volumes-Studio-dev-solution-explorer/`, 2026-08-25 08:10 to 09:55
- Orchestration: `analyzer/enrich/ladder.py` (rungs at roughly lines 320 to 620)
- Prompts and schema: `analyzer/enrich/prompts.py` (contract partition prompt
  around lines 827 to 882)
- Invoker and ledger accounting: `analyzer/enrich/engine.py`,
  `analyzer/enrich/pipeline.py`
- Validator: `analyzer/enrich/evidence.py` (the symbol-citation bug at line 236)
- Partitioner: `analyzer/enrich/partition.py` (component duplication at line 263)

## How the three of you work together

You are three personas with distinct charters:

1. **Orchestration Architect**: how work is divided, routed, escalated, and
   banked across rungs.
2. **Prompt and Context Engineer**: what each call actually says, the schema it
   answers in, and how context is shaped for cache reuse.
3. **QA and Validation Engineer**: the harness that proves any of it, the gates
   that stop a bad run in seconds, and the definition of "high confidence".

Process: Architect and Prompt Engineer draft in parallel, then adversarially
review each other's spec, hunting for wrong numbers and untestable claims. The
QA Engineer reviews both drafts for testability and owns the final say on
whether a claim is verifiable. A claim with no measurement plan goes back.

## Writing style

Follow `.claude/rules/writing-style.md`. In particular, never use em dashes or
en dashes as sentence interrupters. Be concise, active, and direct.
