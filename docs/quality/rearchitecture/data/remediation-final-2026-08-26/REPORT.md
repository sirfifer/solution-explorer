# Enrichment Run Report: polyglot

Commit `e1dbb70df6e7bc1e1202ccb9d0e59f09dde7d1ab`, snapshot 2026-08-27T05:51:26.802866+00:00, engine version 1.

**Determination: NOT-DONE**

The map now supports a reader walking every planted language, following the single web→api HTTP edge, and understanding the fixture's intent — the tours frame everything as 'exists to exercise X' and the census shows all 9 items grounded with no escalations. What it does not yet support is trusting the parity anchor's cross-component claims: independent adjudication struck down 4 of 6 spot-checked claims (67% disagreement), all on services/api, all with the same defect — fixture-global superlatives ('only capability', 'highest inbound count', 'the caller is services/web/src') backed only by component-local evidence. The root component's identity verification also failed outright, and 4 of 5 findings checks came back refuted. Since the whole point of this map is to be a deterministic parity baseline, ungrounded claims on its anchor component and an unverified root are exactly the things a P4-7 diff would trip over. The fix is concrete and already scoped: ground the edge from the system-level relationship record and re-verify root against docker-compose.yml, which fits well inside the remaining budget.

## What this run cost

20 model invocation(s), $2.7219 API-equivalent.

> Costs are API-equivalent units reported by the `claude` CLI, metered against the owner's Claude Max subscription. They are a truthful measure of how much subscription usage this run consumed. They are not money spent.

**The run cost ceiling was reached.** Work below was left undone and is recorded as skipped, not as complete.

## Who did the work

| Model | Calls | Targets | Fresh in | Cached in | Out | Share | Wall | API-equiv |
|---|---|---|---|---|---|---|---|---|
| anthropic-claude-cli:opus | 12 | 20 | 49,424 | 40,820 | 5,246 | 41% | 1.4m | $0.67 |
| anthropic-claude-cli:sonnet | 3 | 12 | 69,168 | 14,482 | 4,452 | 37% | 0.7m | $0.50 |
| anthropic-claude-cli:fable | 5 | 4 | 35,308 | 8,786 | 7,995 | 22% | 2.2m | $1.56 |

20 invocation(s) moved 235,681 tokens in 4.4 minutes of model time.

Delivered response payload: 49,603 UTF-8 bytes total. 20 call(s) exercised the compact transport gate, with 0 violation(s).

Prompt cache: 64,088 tokens read and 153,862 written (read/write 0.42). Only measured reads are counted as savings.

Delivered JSON is schema- and byte-bounded. Billed output also includes hidden reasoning; the Claude CLI exposes no per-call max_tokens below its provider ceiling, so billed-token reduction is measured and gated against the baseline, not falsely called a transport guarantee.

**anthropic-claude-cli:opus** did the most of it, 41% of all tokens across p2_ladder:opus, p3_adjudication:grounding-spot-check, p3_adjudication:substitution-check, p3_adjudication:verify-edges, p3_adjudication:verify-findings, p3_adjudication:verify-identity.

Failed invocations by model: anthropic-claude-cli:fable (1). These consumed allowance and produced nothing.

### What this costs the account

The dollar column above is an API-equivalent price. No card was charged: this work was metered against a Claude subscription, and a subscription is an allowance that refills weekly, not a balance. On Max plans Sonnet and Opus draw from **separate** weekly buckets, so the split above matters more than the total.

_This run has not been measured against the account._ To turn this into a share of the weekly allowance: take a /usage reading immediately before the run, keep hands off the account for its duration, take a second reading immediately after, and record the difference with scripts/usage-budget.py calibrate. Nothing else measures a subscription; the dollar figures here are API-equivalent prices for work that was never billed at API rates.

## What the climbing cost

3 item(s) climbed past the bulk rung, consuming 11,520 tokens and $0.12 API-equivalent above it, roughly $0.042 per climb.

On a Max plan Sonnet and Opus draw from **separate** weekly buckets, so an escalation avoided is worth more than its price: it stops consuming the scarcer of the two.

### Why the rest climbed

For each trigger, the question worth asking before the next run is not "was the harder model right" but **what would the cheaper rung have needed to get this right**. That is a context question far more often than it is a capability question.

| Trigger | Meaning | Suspect | Items | Most frequent question |
|---|---|---|---|---|
| E3 | contradiction: evidence contradicts a deterministic fact or another claim | context | 2 | why_matters |
| E2 | ungrounded: an answer whose evidence the tier could not cite | context | 1 | next_step |

`context` means the tier had the facts and still could not ground, cite or reconcile them, so the prompt is the suspect before the model is. `reasoning` means the difficulty looks real and escalation did its job.

## Item census

| Terminal state | Items |
|---|---|
| grounded@opus | 2 |
| grounded@sonnet | 7 |

9 of 9 items grounded (100.0%).

## Criteria

| Id | Verdict | Criterion | Reasoning |
|---|---|---|---|
| s1 | UNKNOWN | The map states explicitly that this is a test fixture for the analyzer, and every component description is framed as 'exists to exercise X' rather than as production functionality. | the determination did not answer this criterion |
| s2 | UNKNOWN | All eleven languages present in the tree (python, typescript, javascript, go, rust, ruby, swift, plus markdown/yaml/toml/json) are attributed to the correct component, with none silently dropped. | the determination did not answer this criterion |
| s3 | UNKNOWN | The web→api HTTP relationship is named with its direction and protocol, and the map notes it is the fixture's sole cross-component edge. | the determination did not answer this criterion |
| s4 | UNKNOWN | The 'root' component's 'listens on a port' entry-point claim is either corrected or flagged as an attribution of docker-compose's db/cache port bindings, not left as-is. | the determination did not answer this criterion |
| s5 | UNKNOWN | The 'zone of uselessness' finding on services/web/src is contextualized as expected for a fixture (nothing consumes the web client by design), not surfaced as an architectural defect. | the determination did not answer this criterion |
| u1 | MET | Every enrichment target reached a terminal contract state. | every enrichment target reached a terminal contract state |
| u2 | UNMET | Claims are grounded in evidence that checks out. | 100.0% of items grounded; adjudication would not stand behind 77.8% of the claims it sampled |
| u3 | MET | What could not be established is visible as an honest gap, with a reason a reader can act on. | all 0 honest gap(s) carry a reason a reader can act on |

## Escalations

| Target | Climbed | Triggers | Terminal |
|---|---|---|---|
| apps/ios | sonnet:escalate -> opus |  | grounded@opus |
| root | sonnet:escalate -> opus:grounded -> sonnet |  | grounded@sonnet |
| services/web/src | sonnet:escalate -> opus |  | grounded@opus |

## Iterations

### Round 1 (forced)

**Target:** Eliminate the four unsupported cross-component claims on services/api by re-grounding them in the system-level relationship and capability records, and get root's identity verification to confirmed — measurable as a re-adjudication pass with zero unsupported claims and no failed identity targets.

**Measured delta:** {"changed": 0, "targets": [], "state_changes": {}, "rung_moves": ["root"], "grounded_before": 9, "grounded_after": 9, "cost_usd": 0.556452, "adjudication_cost_usd": 0.230488}

**Perceived delta (judgment, not measurement):** Eliminate the four unsupported cross-component claims on services/api by re-grounding them in the system-level relationship and capability records, and get root's identity verification to confirmed — measurable as a re-adjudication pass with zero unsupported claims and no failed identity targets.

This round produced **no measurable gain**. Recorded as such rather than as work done.


## Work orders

| Issued by | Lens | Expected effect | Scope | Executed | Changed anything |
|---|---|---|---|---|---|
| P4 | Ground the web→api edge from the system-level relationship record (source, targe | truth: the adjudicator's unsupported-claim count on services | 2 | no | no |
| P4 | Verify each tail component's language attribution and file citations to the same | truth: grounded fraction across band-3/4/5 components reache | 4 | no | no |
| P5 | Ground the web→api edge from the system-level relationship record (source, targe | truth: adjudication disagreement rate drops from 0.667 towar | 3 | yes | no |

## Parser-first findings

_No parser-first findings were raised._

## Identity flags

_No identity flags: the tiers found no parser-owned value worth disputing._

## Work ledger

| Phase | Rung | Binding | Targets | Tokens in | Tokens out | Cost | Wall s | Retries |
|---|---|---|---|---|---|---|---|---|
| p1_orientation |  | anthropic-claude-cli:fable | 1 | 8903 | 2059 | 0.2839 | 32.1 | 0 |
| p2_ladder | 2a | anthropic-claude-cli:sonnet | 8 | 11648 | 3628 | 0.1310 | 31.5 | 0 |
| p2_ladder | 2a | anthropic-claude-cli:sonnet | 1 | 5515 | 159 | 0.0384 | 3.8 | 0 |
| p2_ladder | opus | anthropic-claude-cli:opus | 3 | 11076 | 444 | 0.1249 | 8.3 | 0 |
| p3_adjudication | verify-identity | anthropic-claude-cli:opus | 3 | 7657 | 2296 | 0.1361 | 27.8 | 0 |
| p3_adjudication | verify-edges | anthropic-claude-cli:opus | 1 | 2774 | 98 | 0.0337 | 3.9 | 0 |
| p3_adjudication | verify-findings | anthropic-claude-cli:opus | 5 | 4232 | 605 | 0.0622 | 9.5 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4086 | 341 | 0.0540 | 5.7 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2192 | 78 | 0.0269 | 2.9 | 0 |
| p4_synthesis | narrative | anthropic-claude-cli:fable | 1 | 2290 | 722 | 0.0874 | 11.6 | 0 |
| p4_synthesis | spine | anthropic-claude-cli:fable | 0 | 8518 | 3050 | 0.3331 | 37.8 | 0 |
| p5_determination |  | anthropic-claude-cli:fable | 1 | 15597 | 2164 | 0.4209 | 27.9 | 0 |
| work_order | P5 | anthropic-claude-cli:sonnet | 3 | 52005 | 665 | 0.3260 | 8.2 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 3392 | 401 | 0.0479 | 6.3 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 4086 | 349 | 0.0542 | 5.8 | 0 |
| p3_adjudication | grounding-spot-check | anthropic-claude-cli:opus | 1 | 3460 | 404 | 0.0488 | 6.5 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2129 | 66 | 0.0259 | 2.9 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2192 | 77 | 0.0269 | 2.9 | 0 |
| p3_adjudication | substitution-check | anthropic-claude-cli:opus | 1 | 2148 | 87 | 0.0267 | 3.3 | 0 |
| p5_determination |  | anthropic-claude-cli:fable | 1 | 0 | 0 | 0.4328 | 24.2 | 0 |

## Lessons

Scrub-safe abstractions only: patterns and counts, never the subject's paths, identifiers or code.

- **escalation-trigger**: E2 (count=1, of_total=9)
- **escalation-trigger**: E3 (count=2, of_total=9)
- **inter-tier-disagreement**: claims adjudication would not stand behind (rate=0.7778, sampled=18)
- **forced-iteration**: a forced improvement round produced no measurable gain (round=1)
