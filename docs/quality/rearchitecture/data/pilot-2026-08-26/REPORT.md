# Enrichment Run Report: polyglot

Commit `e1dbb70df6e7bc1e1202ccb9d0e59f09dde7d1ab`, snapshot 2026-08-27T04:00:11.723543+00:00, engine version 1.

**Determination: NOT-DONE**

The map already supports its core reader task: a developer can walk the coverage tour and confirm every fixture language is detected, follow the single web-to-API HTTP edge (independently confirmed by edge verification), and see the db/cache infrastructure framed at root. What it does not yet support is trusting the services/api summary as parity-snapshot material: 3 of 4 adjudicated claims on that component are unsupported by their own citations (a 75% spot-check disagreement rate), because the summary restates cross-file facts without cross-file evidence. There is also one honest gap ('place' on services/web) that is closable from README/docker-compose evidence at near-zero cost. Both fixes have concrete, already-drafted work orders with predictable effects, so 'not-done' is legal and honest. Budgets are trimmed to fit the remaining $1.26.

## What this run cost

15 model invocation(s), $2.1505 API-equivalent.

> Costs are API-equivalent units reported by the `claude` CLI, metered against the owner's Claude Max subscription. They are a truthful measure of how much subscription usage this run consumed. They are not money spent.

## Who did the work

| Model | Calls | Targets | Fresh in | Cached in | Out | Share | Wall | API-equiv |
|---|---|---|---|---|---|---|---|---|
| anthropic-claude-cli:fable | 6 | 12 | 56,873 | 20,910 | 10,925 | 60% | 2.5m | $1.72 |
| anthropic-claude-cli:opus | 7 | 9 | 19,608 | 14,652 | 3,629 | 26% | 1.6m | $0.30 |
| anthropic-claude-cli:sonnet | 2 | 9 | 20,578 | 0 | 221 | 14% | 0.5m | $0.13 |

15 invocation(s) moved 147,396 tokens in 4.6 minutes of model time.

Delivered response payload: 34,891 UTF-8 bytes total. 3 call(s) exercised the compact transport gate, with 0 violation(s).

Prompt cache: 35,562 tokens read and 97,035 written (read/write 0.37). Only measured reads are counted as savings.

Delivered JSON is schema- and byte-bounded. Billed output also includes hidden reasoning; the Claude CLI exposes no per-call max_tokens below its provider ceiling, so billed-token reduction is measured and gated against the baseline, not falsely called a transport guarantee.

**anthropic-claude-cli:fable** did the most of it, 60% of all tokens across p1_orientation, p2_ladder:fable, p4_synthesis:narrative, p4_synthesis:spine, p5_determination.

Failed invocations by model: anthropic-claude-cli:opus (2), anthropic-claude-cli:sonnet (1). These consumed allowance and produced nothing.

### What this costs the account

The dollar column above is an API-equivalent price. No card was charged: this work was metered against a Claude subscription, and a subscription is an allowance that refills weekly, not a balance. On Max plans Sonnet and Opus draw from **separate** weekly buckets, so the split above matters more than the total.

_This run has not been measured against the account._ To turn this into a share of the weekly allowance: take a /usage reading immediately before the run, keep hands off the account for its duration, take a second reading immediately after, and record the difference with scripts/usage-budget.py calibrate. Nothing else measures a subscription; the dollar figures here are API-equivalent prices for work that was never billed at API rates.

## What the climbing cost

9 item(s) climbed past the bulk rung, consuming 26,999 tokens and $0.66 API-equivalent above it, roughly $0.073 per climb.

On a Max plan Sonnet and Opus draw from **separate** weekly buckets, so an escalation avoided is worth more than its price: it stops consuming the scarcer of the two.

### Why the rest climbed

For each trigger, the question worth asking before the next run is not "was the harder model right" but **what would the cheaper rung have needed to get this right**. That is a context question far more often than it is a capability question.

| Trigger | Meaning | Suspect | Items | Most frequent question |
|---|---|---|---|---|
| E1 | no-answer: a required question the tier could not answer at all | reasoning | 8 | purpose |
| E2 | ungrounded: an answer whose evidence the tier could not cite | context | 2 | place |

`context` means the tier had the facts and still could not ground, cite or reconcile them, so the prompt is the suspect before the model is. `reasoning` means the difficulty looks real and escalation did its job.

## Item census

| Terminal state | Items |
|---|---|
| grounded@fable | 8 |
| honest-gap | 1 |

8 of 9 items grounded (88.9%).

## Criteria

| Id | Verdict | Criterion | Reasoning |
|---|---|---|---|
| s1 | MET | Every one of the 11 languages (python, typescript, javascript, go, rust, ruby, swift, plus markdown/yaml/toml/json config-docs) is attributed to at least one mapped component, because the fixture exists precisely to exercise each tree-sitter grammar. | Every code language maps to a specific component with a cited file, and the config-doc languages are covered at root. No language is absent. |
| s2 | MET | The web-to-API HTTP call is named as a relationship with its protocol, since it is the only inter-component relationship the fixture declares. | The single HTTP edge is present, protocol and port are named, and independent adjudication confirmed the edge itself. |
| s3 | MET | Every component description identifies the code as fixture/stub material, not as a real product feature, and stays consistent with the README's one-line-per-component layout. | Descriptions stay in fixture register with no invented users or business purpose; the adjudication disputes are about citation coverage, not fabricated narrative. |
| s4 | UNKNOWN | The docker-compose infrastructure (db, cache) and the API's Postgres driver dependency are surfaced, because they are the fixture's only infrastructure and external-dependency signals. | The db/cache half is clearly surfaced, but nothing in the record shows the API's Postgres driver dependency being captured, so this cannot be called met. |
| s5 | UNKNOWN | Enrichment spend per component stays minimal and roughly flat across components rather than following the importance ranking, because no component here is genuinely more important than another. | Uniform rung suggests flat treatment, but no spend data exists in the record to verify the distribution, so the honest answer is unknown. |
| u1 | MET | Every enrichment target reached a terminal contract state. | every enrichment target reached a terminal contract state |
| u2 | UNMET | Claims are grounded in evidence that checks out. | 88.9% of items grounded; adjudication would not stand behind 75.0% of the claims it sampled |
| u3 | MET | What could not be established is visible as an honest gap, with a reason a reader can act on. | all 1 honest gap(s) carry a reason a reader can act on |

## Escalations

| Target | Climbed | Triggers | Terminal |
|---|---|---|---|
| apps/ios | sonnet:escalate -> fable |  | grounded@fable |
| libs/core | sonnet:escalate -> fable |  | grounded@fable |
| libs/rubylib | sonnet:escalate -> fable |  | grounded@fable |
| root | sonnet:escalate -> fable |  | grounded@fable |
| services/api | sonnet:escalate -> fable |  | grounded@fable |
| services/web | sonnet:escalate -> fable | E2 | honest-gap |
| services/web/src | sonnet:escalate -> fable |  | grounded@fable |
| services/worker | sonnet:escalate -> fable |  | grounded@fable |
| services/web/src|services/api|http | sonnet:escalate -> fable |  | grounded@fable |

## Iterations

_No improvement rounds ran._

## Work orders

| Issued by | Lens | Expected effect | Scope | Executed | Changed anything |
|---|---|---|---|---|---|
| P4 | Rewrite the services/api summary to claim only what its own cited evidence suppo | truth: adjudicator disagreement count on services/api drops  | 1 | no | no |
| P4 | Answer services/web's 'place' question using the README's one-line-per-component | truth: honest-gap count moves from 1 to 0 with the grounded  | 2 | no | no |
| P5 | Rewrite the services/api summary to claim only what its own cited evidence suppo | truth: adjudicator disagreement count on services/api drops  | 1 | no | no |
| P5 | Answer services/web's 'place' question using the README's one-line-per-component | truth: honest-gap count moves from 1 to 0, grounded fraction | 2 | no | no |

## Parser-first findings

_No parser-first findings were raised._

## Identity flags

_No identity flags: the tiers found no parser-owned value worth disputing._

## Work ledger

| Phase | Rung | Binding | Targets | Tokens in | Tokens out | Cost | Wall s | Retries |
|---|---|---|---|---|---|---|---|---|
| p1_orientation |  | anthropic-claude-cli:fable | 1 | 8461 | 1921 | 0.2682 | 29.4 | 0 |
| p2_ladder | 2a | anthropic-claude-cli:sonnet | 8 | 0 | 0 | 0.0000 | 25.6 | 0 |
| p2_ladder | 2a | anthropic-claude-cli:sonnet | 1 | 20578 | 221 | 0.1275 | 3.9 | 0 |
| p2_ladder | opus | anthropic-claude-cli:opus | 5 | 0 | 0 | 0.0000 | 26.5 | 0 |
| p2_ladder | opus | anthropic-claude-cli:opus | 4 | 0 | 0 | 0.0000 | 18.9 | 0 |
| p2_ladder | fable | anthropic-claude-cli:fable | 5 | 18587 | 1827 | 0.4657 | 24.3 | 0 |
| p2_ladder | fable | anthropic-claude-cli:fable | 4 | 5023 | 1562 | 0.1937 | 19.4 | 0 |
| p3_adjudication | verify-identity | anthropic-claude-cli:opus | 0 | 7265 | 2019 | 0.1253 | 23.8 | 0 |
| p3_adjudication | verify-edges | anthropic-claude-cli:opus | 0 | 2691 | 84 | 0.0322 | 2.8 | 0 |
| p3_adjudication | verify-findings | anthropic-claude-cli:opus | 0 | 4207 | 728 | 0.0648 | 10.9 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 0 | 3325 | 735 | 0.0554 | 13.4 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 0 | 2120 | 63 | 0.0256 | 2.6 | 0 |
| p4_synthesis | narrative | anthropic-claude-cli:fable | 1 | 2265 | 628 | 0.0818 | 10.1 | 0 |
| p4_synthesis | spine | anthropic-claude-cli:fable | 0 | 8212 | 2453 | 0.2965 | 32.2 | 0 |
| p5_determination |  | anthropic-claude-cli:fable | 1 | 14325 | 2534 | 0.4138 | 32.1 | 0 |

## Lessons

Scrub-safe abstractions only: patterns and counts, never the subject's paths, identifiers or code.

- **escalation-trigger**: E1 (count=8, of_total=9)
- **escalation-trigger**: E2 (count=2, of_total=9)
- **inter-tier-disagreement**: claims adjudication would not stand behind (rate=0.75, sampled=4)
