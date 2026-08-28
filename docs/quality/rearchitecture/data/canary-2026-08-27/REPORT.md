# Enrichment Run Report: polyglot

Commit `2c01ee0398acf1be95c38ab6082d6b194a6ab53c`, snapshot 2026-08-27T18:06:52.204214+00:00, engine version 1.

**Determination: DONE**

The map now serves its test-oracle purpose: an analyzer maintainer can confirm every README layout entry was detected with the right language, manifest, and type, that the single web-to-API HTTP edge exists with no invented companions, and that every description stays inside what the stub files actually contain. The census is fully grounded (11/11) and round 1 met its stated target, cutting adjudicator disagreement from 22.6% to 9.7% and unsupported claims from 14 to 6. The residual 6 unsupported claims are all the same benign citation-scope defect: why_matters sentences saying a component is listed 'alongside the other six fixture components' while citing only that component's own README line (plus one over-cautious next_step on services/web/src). The enumeration itself is established and supported on root's place claim, so no reader is misled — the evidence pointer is merely narrower than the sentence. A further round rewriting those four sentences would polish the disagreement number but not change what the map supports a reader doing, and the brief explicitly warns that extra enrichment on this fixture is fabrication risk, not value. What the map does not settle: the independent identity verifier returned 'uncertain' for three components and failed on root, and three findings were refuted — those are verifier-owned verdicts a work order cannot repair, and they are visible rather than papered over.

## What this run cost

48 model invocation(s), $3.7810 API-equivalent.

> Costs are API-equivalent units reported by the `claude` CLI, metered against the owner's Claude Max subscription. They are a truthful measure of how much subscription usage this run consumed. They are not money spent.

## Who did the work

| Model | Calls | Targets | Fresh in | Cached in | Out | Share | Wall | API-equiv |
|---|---|---|---|---|---|---|---|---|
| anthropic-claude-cli:opus | 39 | 48 | 146,707 | 162,293 | 10,636 | 65% | 3.2m | $1.90 |
| anthropic-claude-cli:fable | 5 | 4 | 44,677 | 30,518 | 10,832 | 18% | 2.5m | $1.49 |
| anthropic-claude-cli:sonnet | 4 | 23 | 46,711 | 33,430 | 5,444 | 17% | 0.8m | $0.40 |

48 invocation(s) moved 491,248 tokens in 6.5 minutes of model time.

Delivered response payload: 66,258 UTF-8 bytes total. 48 call(s) exercised the compact transport gate, with 0 violation(s).

Prompt cache: 226,241 tokens read and 237,999 written (read/write 0.95). Only measured reads are counted as savings.

Delivered JSON is schema- and byte-bounded. Billed output also includes hidden reasoning; the Claude CLI exposes no per-call max_tokens below its provider ceiling, so billed-token reduction is measured and gated against the baseline, not falsely called a transport guarantee.

**anthropic-claude-cli:opus** did the most of it, 65% of all tokens across p2_ladder:opus, p3_adjudication:grounding-spot-check, p3_adjudication:substitution-check, p3_adjudication:verify-edges, p3_adjudication:verify-findings, p3_adjudication:verify-identity.

### What this costs the account

The dollar column above is an API-equivalent price. No card was charged: this work was metered against a Claude subscription, and a subscription is an allowance that refills weekly, not a balance. On Max plans Sonnet and Opus draw from **separate** weekly buckets, so the split above matters more than the total.

_This run has not been measured against the account._ To turn this into a share of the weekly allowance: take a /usage reading immediately before the run, keep hands off the account for its duration, take a second reading immediately after, and record the difference with scripts/usage-budget.py calibrate. Nothing else measures a subscription; the dollar figures here are API-equivalent prices for work that was never billed at API rates.

## What the climbing cost

2 item(s) climbed past the bulk rung, consuming 10,949 tokens and $0.12 API-equivalent above it, roughly $0.058 per climb.

On a Max plan Sonnet and Opus draw from **separate** weekly buckets, so an escalation avoided is worth more than its price: it stops consuming the scarcer of the two.

### Why the rest climbed

For each trigger, the question worth asking before the next run is not "was the harder model right" but **what would the cheaper rung have needed to get this right**. That is a context question far more often than it is a capability question.

| Trigger | Meaning | Suspect | Items | Most frequent question |
|---|---|---|---|---|
| E3 | contradiction: evidence contradicts a deterministic fact or another claim | context | 2 | mechanism |

`context` means the tier had the facts and still could not ground, cite or reconcile them, so the prompt is the suspect before the model is. `reasoning` means the difficulty looks real and escalation did its job.

## Item census

| Terminal state | Items |
|---|---|
| grounded@opus | 1 |
| grounded@sonnet | 10 |

11 of 11 items grounded (100.0%).

## Criteria

| Id | Verdict | Criterion | Reasoning |
|---|---|---|---|
| s1 | MET | The map names every language-bearing component the README lists (api, web, worker, core, rubylib, ios, compose db and cache) and assigns each its correct language and manifest, because each one exists solely to prove a parser path works. | Every README layout entry appears with the correct language and manifest; no tree-sitter path is missing. |
| s2 | MET | The web-to-API HTTP call is represented as the system's one inter-service relationship, and no invented relationships appear alongside it. | The one declared cross-component edge is present and independently confirmed, with no hallucinated extras. |
| s3 | MET | Every component's map entry describes it as a fixture exercising a detection path, never as a real product capability (no invented business purpose for the worker, the Rust lib, or the iOS app). | No component description invents business behaviour beyond the stub source. |
| s4 | MET | Component types match their triggering signal: services/api is typed by its port bind, compose/db and compose/cache by their docker-compose declarations, services/worker by main.go, the libraries by their manifests. | Each type traces to its intended triggering signal. |
| s5 | MET | The map states, prominently, that this is a CI test fixture rather than a deployable system, and its overview does not read like a startup's architecture. | The map's top-level framing presents a CI test fixture anchoring the parity snapshot, not a product architecture. |
| u1 | MET | Every enrichment target reached a terminal contract state. | every enrichment target reached a terminal contract state |
| u2 | MET | Claims are grounded in evidence that checks out. | 100.0% of items grounded; adjudication would not stand behind 9.7% of the claims it sampled |
| u3 | MET | What could not be established is visible as an honest gap, with a reason a reader can act on. | all 0 honest gap(s) carry a reason a reader can act on |

## Escalations

| Target | Climbed | Triggers | Terminal |
|---|---|---|---|
| services/api | sonnet:escalate -> opus |  | grounded@opus |
| services/web | sonnet:escalate -> opus:grounded -> sonnet |  | grounded@sonnet |

## Iterations

### Round 1 (forced)

**Target:** Reduce the adjudicator's unsupported-claim count from 14 to at most 6 by grounding the seven-language coverage claim in a citable README fact on root and replacing the compose flavor adjectives with the literal compose-file image declarations — measurable by re-running the spot-check and seeing the disagreement rate fall below 10%.

**Measured delta:** {"changed": 0, "targets": [], "state_changes": {}, "rung_moves": ["services/web"], "payload_changes": ["apps/ios", "compose/cache", "compose/db", "libs/core", "libs/rubylib", "root", "services/web", "services/web/src", "services/web/src|services/api|http", "services/worker"], "grounded_before": 11, "grounded_after": 11, "cost_usd": 0.994186, "adjudication_cost_usd": 0.805462, "adjudication_disagreement_before": 0.225806, "adjudication_disagreement_after": 0.096774}

**Perceived delta (judgment, not measurement):** Reduce the adjudicator's unsupported-claim count from 14 to at most 6 by grounding the seven-language coverage claim in a citable README fact on root and replacing the compose flavor adjectives with the literal compose-file image declarations — measurable by re-running the spot-check and seeing the disagreement rate fall below 10%.


## Work orders

| Issued by | Lens | Expected effect | Scope | Executed | Changed anything |
|---|---|---|---|---|---|
| P4 | Extract the README layout section's explicit language enumeration as a fact on r | truth: adjudicator disagreement rate drops by four component | 5 | no | no |
| P4 | Read the docker-compose.yml service blocks and record the literal image field (o | truth: two disputed purpose claims move to supported, and th | 2 | no | no |
| P5 | Extract the README layout section's explicit language enumeration as a citable f | truth: the unsupported-claim count for the scoped targets de | 10 | yes | yes |
| P5 | Read the docker-compose.yml service blocks and record the literal image field (o | truth: up to four disputed compose claims move to supported  | 2 | yes | yes |
| P5-deterministic-repair | Repair only the independently unsupported claims. Narrow each claim until every  | truth: the unsupported-claim count for the scoped targets de | 6 | no | no |

## Parser-first findings

_No parser-first findings were raised._

## Identity flags

_No identity flags: the tiers found no parser-owned value worth disputing._

## Work ledger

| Phase | Rung | Binding | Targets | Tokens in | Tokens out | Cost | Wall s | Retries |
|---|---|---|---|---|---|---|---|---|
| p1_orientation |  | anthropic-claude-cli:fable | 1 | 2 | 2125 | 0.1188 | 34.2 | 0 |
| p2_ladder | 2a | anthropic-claude-cli:sonnet | 10 | 16827 | 3706 | 0.1670 | 30.9 | 0 |
| p2_ladder | 2a | anthropic-claude-cli:sonnet | 1 | 5877 | 136 | 0.0405 | 3.6 | 0 |
| p2_ladder | opus | anthropic-claude-cli:opus | 2 | 10756 | 193 | 0.1151 | 4.5 | 0 |
| p3_adjudication | verify-identity | anthropic-claude-cli:opus | 5 | 4412 | 3209 | 0.1292 | 35.1 | 0 |
| p3_adjudication | verify-edges | anthropic-claude-cli:opus | 1 | 2721 | 88 | 0.0329 | 2.8 | 0 |
| p3_adjudication | verify-findings | anthropic-claude-cli:opus | 5 | 4232 | 469 | 0.0588 | 7.5 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4197 | 184 | 0.0513 | 3.5 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4371 | 465 | 0.0602 | 7.4 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4220 | 256 | 0.0534 | 4.9 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4153 | 196 | 0.0511 | 4.0 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4401 | 182 | 0.0534 | 3.5 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 6267 | 473 | 0.0808 | 7.7 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4835 | 415 | 0.0640 | 5.8 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4558 | 354 | 0.0595 | 5.9 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4524 | 195 | 0.0551 | 4.2 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4054 | 187 | 0.0498 | 3.6 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 3309 | 405 | 0.0471 | 7.0 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2109 | 54 | 0.0245 | 2.5 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2131 | 68 | 0.0261 | 2.6 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2161 | 65 | 0.0263 | 2.7 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2109 | 111 | 0.0269 | 3.2 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2097 | 89 | 0.0262 | 3.3 | 0 |
| p4_synthesis | narrative | anthropic-claude-cli:fable | 1 | 2307 | 794 | 0.0914 | 11.9 | 0 |
| p4_synthesis | spine | anthropic-claude-cli:fable | 0 | 10499 | 3228 | 0.3832 | 41.5 | 0 |
| p5_determination |  | anthropic-claude-cli:fable | 1 | 22282 | 2467 | 0.5742 | 32.8 | 0 |
| work_order | P5 | anthropic-claude-cli:sonnet | 10 | 17713 | 1257 | 0.1397 | 11.3 | 0 |
| work_order | P5 | anthropic-claude-cli:sonnet | 2 | 6294 | 345 | 0.0490 | 5.2 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4407 | 214 | 0.0543 | 3.7 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4220 | 151 | 0.0507 | 3.2 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4061 | 195 | 0.0501 | 3.8 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4252 | 188 | 0.0520 | 3.7 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4551 | 196 | 0.0554 | 4.0 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 7401 | 388 | 0.0909 | 6.7 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4915 | 150 | 0.0583 | 3.3 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4523 | 655 | 0.0666 | 9.7 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4192 | 191 | 0.0514 | 3.6 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 3248 | 99 | 0.0388 | 3.1 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2157 | 64 | 0.0262 | 2.6 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2129 | 65 | 0.0260 | 2.5 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2132 | 70 | 0.0261 | 2.6 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2127 | 73 | 0.0261 | 2.5 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2130 | 59 | 0.0258 | 3.3 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2184 | 55 | 0.0263 | 2.6 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2235 | 51 | 0.0292 | 3.2 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2120 | 55 | 0.0256 | 2.6 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2106 | 59 | 0.0256 | 2.5 | 0 |
| p5_determination |  | anthropic-claude-cli:fable | 1 | 9587 | 2218 | 0.3200 | 30.0 | 0 |

## Lessons

Scrub-safe abstractions only: patterns and counts, never the subject's paths, identifiers or code.

- **escalation-trigger**: E3 (count=2, of_total=11)
- **inter-tier-disagreement**: claims adjudication would not stand behind (rate=0.0968, sampled=62)

