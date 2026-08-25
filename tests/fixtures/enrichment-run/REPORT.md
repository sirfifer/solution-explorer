# Enrichment Run Report: polyglot

Commit `4f6ef44ff277534ceb2d8007d92f57fc123fa8d1`, snapshot 2026-08-21T00:00:00+00:00, engine version 1.

**Determination: DONE**

The census shows the map supports a reader orienting and finding the service boundary. It does not yet support reasoning about failure modes.

## What this run cost

26 model invocation(s), $0.2600 API-equivalent.

> Costs are API-equivalent units reported by the `claude` CLI, metered against the owner's Claude Max subscription. They are a truthful measure of how much subscription usage this run consumed. They are not money spent.

## Who did the work

| Model | Calls | Targets | Fresh in | Cached in | Out | Share | Wall | API-equiv |
|---|---|---|---|---|---|---|---|---|
| anthropic-claude-cli:opus | 18 | 1 | 21,600 | 0 | 5,400 | 69% | 0.0m | $0.18 |
| anthropic-claude-cli:fable | 6 | 5 | 7,200 | 0 | 1,800 | 23% | 0.0m | $0.06 |
| anthropic-claude-cli:sonnet | 2 | 10 | 2,400 | 0 | 600 | 8% | 0.0m | $0.02 |

26 invocation(s) moved 39,000 tokens in 0.0 minutes of model time.

**anthropic-claude-cli:opus** did the most of it, 69% of all tokens across p2_ladder:opus, p3_adjudication:grounding-spot-check, p3_adjudication:substitution-check, p3_adjudication:verify-edges, p3_adjudication:verify-findings, p3_adjudication:verify-identity.

### What this costs the account

The dollar column above is an API-equivalent price. No card was charged: this work was metered against a Claude subscription, and a subscription is an allowance that refills weekly, not a balance. On Max plans Sonnet and Opus draw from **separate** weekly buckets, so the split above matters more than the total.

_This run has not been measured against the account._ To turn this into a share of the weekly allowance: take a /usage reading immediately before the run, keep hands off the account for its duration, take a second reading immediately after, and record the difference with scripts/usage-budget.py calibrate. Nothing else measures a subscription; the dollar figures here are API-equivalent prices for work that was never billed at API rates.

## What the climbing cost

1 item(s) climbed past the bulk rung, consuming 3,000 tokens and $0.02 API-equivalent above it, roughly $0.020 per climb.

On a Max plan Sonnet and Opus draw from **separate** weekly buckets, so an escalation avoided is worth more than its price: it stops consuming the scarcer of the two.

### Questions the parser should have answered

The best kind of finding here. These are not model problems: the tier itself declared that a deterministic fact would have settled the question. Moving one of these costs no model call at all, and it improves the input to every later stage rather than only this one.

| Question a parser could settle | Items |
|---|---|
| libs/core's language was inferable from its manifest | 1 |

### Why the rest climbed

For each trigger, the question worth asking before the next run is not "was the harder model right" but **what would the cheaper rung have needed to get this right**. That is a context question far more often than it is a capability question.

| Trigger | Meaning | Suspect | Items | Most frequent question |
|---|---|---|---|---|
| E1 | no-answer: a required question the tier could not answer at all | reasoning | 1 | mechanism |

`context` means the tier had the facts and still could not ground, cite or reconcile them, so the prompt is the suspect before the model is. `reasoning` means the difficulty looks real and escalation did its job.

## Item census

| Terminal state | Items |
|---|---|
| grounded@sonnet | 8 |
| honest-gap | 1 |

8 of 9 items grounded (88.9%).

## Criteria

| Id | Verdict | Criterion | Reasoning |
|---|---|---|---|
| s1 | MET | Every language present is named on the component that carries it. | the census grounded identity.language throughout |
| u1 | MET | Every enrichment target reached a terminal contract state. | every enrichment target reached a terminal contract state |
| u2 | MET | Claims are grounded in evidence that checks out. | 88.9% of items grounded; adjudication would not stand behind 0.0% of the claims it sampled |
| u3 | MET | What could not be established is visible as an honest gap, with a reason a reader can act on. | all 1 honest gap(s) carry a reason a reader can act on |

## Escalations

| Target | Climbed | Triggers | Terminal |
|---|---|---|---|
| libs/core | sonnet:escalate -> opus:escalate -> fable | E1 | honest-gap |

## Iterations

### Round 1 (forced)

**Target:** deepen the boundary descriptions on the two services that face outward

**Measured delta:** {"changed": 0, "targets": [], "state_changes": {}, "rung_moves": [], "grounded_before": 8, "grounded_after": 8, "cost_usd": 0.01}

**Perceived delta (judgment, not measurement):** deepen the boundary descriptions on the two services that face outward

This round produced **no measurable gain**. Recorded as such rather than as work done.


## Work orders

| Issued by | Lens | Expected effect | Scope | Executed | Changed anything |
|---|---|---|---|---|---|
| P4 | framework detection on the quiet packages | truth: framework identity verdicts | 2 | no | no |
| P5 | the outward-facing boundary | truth: the grounded fraction should rise | 2 | yes | no |
| P5 | the outward-facing boundary | truth: the grounded fraction should rise | 2 | no | no |

## Parser-first findings

1 observation(s) that deterministic processing could have answered without a model. Each is a capability card.

- `libs/core`: libs/core's language was inferable from its manifest

## Work ledger

| Phase | Rung | Binding | Targets | Tokens in | Tokens out | Cost | Wall s | Retries |
|---|---|---|---|---|---|---|---|---|
| p1_orientation |  | anthropic-claude-cli:fable | 1 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p2_ladder | 2a | anthropic-claude-cli:sonnet | 8 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p2_ladder | opus | anthropic-claude-cli:opus | 1 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p2_ladder | fable | anthropic-claude-cli:fable | 1 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p3_adjudication | verify-identity | anthropic-claude-cli:opus | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p3_adjudication | verify-identity | anthropic-claude-cli:opus | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p3_adjudication | verify-identity | anthropic-claude-cli:opus | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p3_adjudication | verify-edges | anthropic-claude-cli:opus | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p3_adjudication | verify-edges | anthropic-claude-cli:opus | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p3_adjudication | verify-findings | anthropic-claude-cli:opus | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p3_adjudication | verify-findings | anthropic-claude-cli:opus | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p3_adjudication | verify-findings | anthropic-claude-cli:opus | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p3_adjudication | verify-findings | anthropic-claude-cli:opus | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p3_adjudication | verify-findings | anthropic-claude-cli:opus | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p3_adjudication | verify-findings | anthropic-claude-cli:opus | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p3_adjudication | verify-findings | anthropic-claude-cli:opus | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p3_adjudication | verify-findings | anthropic-claude-cli:opus | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p3_adjudication | verify-findings | anthropic-claude-cli:opus | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p3_adjudication | verify-findings | anthropic-claude-cli:opus | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p4_synthesis | narrative | anthropic-claude-cli:fable | 1 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p4_synthesis | spine | anthropic-claude-cli:fable | 0 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p5_determination |  | anthropic-claude-cli:fable | 1 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| work_order | P5 | anthropic-claude-cli:sonnet | 2 | 1200 | 300 | 0.0100 | 0.0 | 0 |
| p5_determination |  | anthropic-claude-cli:fable | 1 | 1200 | 300 | 0.0100 | 0.0 | 0 |

## Lessons

Scrub-safe abstractions only: patterns and counts, never the subject's paths, identifiers or code.

- **escalation-trigger**: E1 (count=1, of_total=9)
- **parser-first**: deterministic processing could have answered this (count=3, of_total=9)
- **inter-tier-disagreement**: claims adjudication would not stand behind (rate=0.0, sampled=8)
- **forced-iteration**: a forced improvement round produced no measurable gain (round=1)

