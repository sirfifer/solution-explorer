# Enrichment Run Report: polyglot

Commit `<commit-of-the-run>`, snapshot 2026-08-21T00:00:00+00:00, engine version 1.

**Determination: DONE**

The census shows the map supports a reader orienting and finding the service boundary. It does not yet support reasoning about failure modes.

## What this run cost

26 model invocation(s), $0.2600 API-equivalent.

> Costs are API-equivalent units reported by the `claude` CLI, metered against the owner's Claude Max subscription. They are a truthful measure of how much subscription usage this run consumed. They are not money spent.

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

