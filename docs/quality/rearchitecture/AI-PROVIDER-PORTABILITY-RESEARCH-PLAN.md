# AI provider portability: research, validation, and implementation plan

**Recorded:** 2026-08-30
**Status:** Accepted future work; deliberately parked
**Near-term operating decision:** Continue using the Claude Max-backed Claude
CLI profile for current UnaMentis work and demos. Provider portability is not a
gate on the current full UnaMentis enrichment run.
**Re-entry trigger:** Resume when subscription diversification becomes a
priority, before demo volume makes one subscription a material constraint, or
before the enrichment service is operated for other people.

## 1. Decision in one page

Solution Explorer should support a single operator-facing provider switch, but
the switch must select a complete execution profile rather than merely replace
a model name. The intended near-term interface is:

```text
analyze.py enhance ... --ai-profile claude-max
analyze.py enhance ... --ai-profile chatgpt-pro
```

The current code is already substantially provider-aware: a rung binding has a
source, model, and effort; providers register invoker builders; retry is shared;
ledger labels are source-qualified; and each ladder rung can be overridden.
What does not yet exist is a second provider implementation or a named profile
that binds the whole execution contract. The current defaults are eight
explicit Claude bindings, so this is not yet a safe one-command switch.

The work is feasible, but it is not a literal executable substitution. Claude
CLI and Codex CLI expose different agent harnesses, isolation controls,
structured-output behavior, cache visibility, usage envelopes, effort scales,
and failure modes. Treating them as identical would recreate the exact classes
of hidden context, lost output, false cost reporting, and cache assumptions the
enrichment-economics work just removed.

The recommended sequence is therefore:

1. Add a thin Codex CLI transport and named profiles without changing the
   provider-neutral enrichment contracts.
2. Prove process isolation, error recovery, accounting, and cache behavior with
   small live probes.
3. Run the same bounded canary through both profiles and compare quality first,
   observability second, and efficiency third.
4. Enable the ChatGPT Pro profile for full runs only after those gates pass.
5. Build API-backed profiles later, as a separate operational and commercial
   phase.

Estimated effort when resumed: **1.5 to 2.5 focused engineering days**, plus a
small set of live probes. A superficial Codex launch could be assembled in
roughly 3 to 5 hours, but that is specifically not the acceptance standard.

## 2. Why this is being parked rather than rejected

The immediate goal is to put a complete, high-quality UnaMentis result in front
of people. Claude Max is the already-proven transport, and adding provider
portability now would consume attention and subscription capacity without
improving that result. Deferral protects the demo path; it does not weaken the
provider-portability decision.

The near-term value is clear:

- use either of the owner's existing subscriptions as capacity permits;
- compare independent providers without rebuilding the enrichment pipeline;
- permit hybrid ladders, including generation by one provider and adjudication
  by another;
- avoid making the architecture depend on Claude-specific terminology or
  envelopes;
- retain the cost, quality, and learning improvements already proven by the
  enrichment-economics engagement.

The longer-term value is also clear but belongs to a different horizon. An
operated product needs API-backed execution with explicit customer or tenant
billing, stable credentials, rate-limit handling, retention choices, and
service-level observability. That work should reuse the same profile contract,
but it must not become a hidden acceptance condition for the subscription-backed
work.

## 3. Non-negotiable priorities

The provider work inherits the enrichment program's priority order.

1. **Quality.** A provider is not accepted because it is cheaper. Grounding,
   target conservation, evidence, disagreement, repair success, synthesis, and
   the final viewer product must not regress. A better model must have room to
   produce a better result without an application rewrite.
2. **Learning and observability.** Every run must retain enough provider,
   orchestration, validation, latency, usage, escalation, repair, and exit data
   to explain what happened and to identify new deterministic work. Compact
   output is good; information starvation is not.
3. **Efficiency.** Once the first two constraints hold, reduce repeated input,
   discarded output, duplicated meaning, excess reasoning, unnecessary calls,
   and avoidable escalation aggressively.
4. **Deterministic migration.** Any fact repeatedly inferred from repository
   evidence should be considered for extraction or derivation. The exit report
   must keep this feedback channel visible regardless of provider.

Budgets are runaway protection, not quality targets. During calibration, a
small estimate miss must not terminate the very probe needed to understand the
provider. Once measured behavior is stable, the profile can define a generous
pause threshold that stops launching new calls, preserves completed work, and
presents decision support for resume or cancel.

## 4. What already exists

The implementation is approximately 70 percent of the way to a genuine
provider abstraction.

### Provider-neutral pieces already shipped

- `ModelSpec` represents `source`, optional pinned `model`, and `effort`.
- `register_provider` and `build_invoker` provide a source-to-transport registry.
- Ledger labels include both source and resolved model binding.
- Unknown sources are rejected before a rung begins spending usage.
- Transport retry, timeout plumbing, schema validation, response-byte budgets,
  target conservation, repair semantics, and ladder orchestration sit above the
  concrete provider.
- `--phase-model KEY=SPEC` permits per-rung experiments and future hybrid runs.
- `source:auto` supports provider-side routing without changing ladder logic.

### Claude-specific pieces that remain

- `DEFAULT_MODELS` binds all eight invoking roles directly to Claude tiers.
- Only `ClaudeCliInvoker` is registered.
- The Run Report's cost note says all usage came from Claude CLI and Claude Max.
- Cache audit predicates assume Claude's reported cache fields and the prefix
  mechanism proven for Claude CLI.
- Some persisted and displayed rung states use model-era terms such as
  `sonnet`, `opus`, and `fable` even though the underlying concepts are bulk,
  escalated, and residue work.
- Authentication, throttle, and transport diagnostics recognize Claude-shaped
  failures.

### One concrete configuration trap

`--model-source` sounds like a whole-ladder switch, but it does not rebind the
existing explicit defaults. `ModelSpec.parse(ModelSpec(...),
default_source=...)` correctly preserves an already-formed spec, and every
default is already formed with the Claude source. Consequently, selecting a
new default source today would still require eight `--phase-model` overrides.

This should not be "fixed" by changing `ModelSpec.parse` globally; that could
silently reinterpret intentional explicit bindings. Named profiles should own
whole-ladder rebinding, while `--model-source` can remain the default only for
otherwise unqualified input.

## 5. The profile abstraction

An AI profile is the smallest honest switching unit. It should define:

```text
profile id
  transport/provider id
  authentication mode
  per-rung model binding
  per-rung reasoning effort
  process and context isolation policy
  prompt-wrapper policy
  stable-prefix/cache strategy and cache capability
  structured-output strategy
  timeout, retry, throttle, and interruption classification
  usage and cost-accounting adapter
  resumable pause/checkpoint behavior
  provider-specific diagnostics retained for the exit report
```

The first profiles should be:

- `claude-max`: the current proven Claude CLI behavior, moved behind an explicit
  profile with no semantic change;
- `chatgpt-pro`: Codex CLI authenticated through the owner's ChatGPT
  subscription, with an isolated non-agentic execution configuration;
- optionally, an internal hybrid profile used only for evaluation, for example
  Codex generation with Claude adjudication.

Per-rung overrides remain available after profile resolution. That preserves
experimentation and avoids turning named profiles into a new hardcoded ladder.
The resolved profile, source, model, effort, and CLI version must be stamped in
every call ledger and Run Report.

## 6. Claude CLI and Codex CLI are not the same transport

| Concern | Current Claude CLI profile | Candidate Codex CLI profile | Required response |
|---|---|---|---|
| Subscription route | Claude CLI on Claude Max | `codex exec` signed in with ChatGPT | Keep subscription and API auth as distinct profiles |
| Invocation | Print mode, prompt on stdin | Non-interactive `codex exec`, prompt on stdin | Separate invokers behind the same `Invoker` result |
| Default behavior | Agent behavior can be disabled with explicit flags | Agent harness includes instructions, tools, workspace context, and config | Construct an isolated, closed-world execution profile |
| Final output | JSON envelope with a `result` field | JSONL events plus optional final-output file | Retain JSONL diagnostics and capture final content separately |
| Structured output | Prompt contract plus in-process validation; selected Claude schema use has known cache interactions | CLI supports output schema | Keep in-process validation initially; test schema failure recovery before relying on CLI enforcement |
| Effort | Claude effort names and measured tier behavior | Codex reasoning-effort configuration and a different scale | Calibrate by quality and behavior, never by matching labels |
| Caching | Stable appended system prefix plus dynamic-system-section exclusion is live-proven | No known identical CLI switch or identical cache envelope | Make cache capability explicit and prove it with live repeats |
| Cost/usage | Claude envelope reports API-equivalent cost and cache usage | Codex event/token fields require fixtures and live confirmation | Normalize common metrics; preserve raw provider metrics; label calculated values |
| Budget | Claude offers a per-call best-effort allowance; run pause remains the real guard | No assumed equivalent | Pause between calls using the shared checkpoint, not inside a response |
| Session behavior | Explicit one-turn session IDs | Ephemeral execution and no resume for ordinary calls | One call, one answer; no hidden accumulating session |

The ChatGPT Pro route must use the authenticated Codex CLI. Calling the OpenAI
Responses API is a separate API-billed route, even when the operator also has a
ChatGPT subscription. This distinction belongs in profile names, reports, and
documentation so a switch never causes an unexpected billing-mode change.

## 7. Codex execution isolation

The largest functional risk is not JSON parsing; it is accidentally invoking a
repository agent when the enrichment rung expects closed-world inference over
the supplied facts.

The Codex invoker should begin from the strictest supported isolated profile:

- ephemeral execution;
- read-only sandbox even though tools should be disabled;
- shell and web search disabled;
- memories disabled;
- project instruction discovery, including `AGENTS.md`, disabled or rooted in
  an empty controlled directory;
- user configuration ignored except for the minimum authentication material;
- MCP servers, plugins, apps, and unrelated skills unavailable;
- a fixed working directory unrelated to the subject repository;
- no session resume for normal ladder calls;
- a thin provider wrapper stating that the supplied facts are the entire
  evidence universe, tools and repository reads are forbidden, and the
  contract response is the only output.

Each isolation setting needs an executable fixture or inspection assertion. A
comment saying a tool is unavailable is not sufficient. One negative live probe
should include a tempting file reference and verify that no tool event or file
read occurs.

## 8. Prompt and contract strategy

Do not create parallel Claude and OpenAI prompt libraries. The semantic prompt,
fact menu, response schema, target-conservation rule, evidence vocabulary,
repair contract, and learning channel remain provider-neutral.

Provider adaptation should be a thin wrapper around that shared body:

- identify the execution as closed-book transformation and analysis;
- define the supplied fact block as the only admissible evidence;
- prohibit tool and repository access;
- require only the contract payload on the final-output channel;
- avoid repeating instructions that the profile already pins stably.

The existing response-byte budgets and semantic-atom design remain useful for
both providers. They control duplicated and discarded text without limiting the
model's ability to discover grounded insights. The exit-analysis contract also
remains common; provider-specific telemetry is additive to it.

## 9. Model and effort calibration

Effort labels are provider-local settings, not comparable units. `high` on one
provider is not evidence that `high` on another has similar latency, reasoning,
output density, or quality.

The first Codex canary should hold model quality high and vary effort by the
nature of the rung. The locally installed catalog at the time of this report
exposes Sol, Terra, and Luna families, with Sol supporting reasoning settings
through `ultra`. A conservative starting hypothesis, to be tested rather than
declared correct, is:

| Rung | Initial candidate | Initial effort hypothesis |
|---|---|---|
| Orientation | highest-quality general Codex model | high |
| Bulk | highest-quality general Codex model | low |
| Escalation | highest-quality general Codex model | high |
| Residue | highest-quality general Codex model | xhigh |
| Adjudication | highest-quality general Codex model | high |
| Synthesis | highest-quality general Codex model | xhigh |
| Determination | highest-quality general Codex model | xhigh |
| Work orders | highest-quality general Codex model | medium |

Only after quality parity should the bulk rung be tested on the faster model
family and work orders on the balanced family. `ultra` should not be used for
this pipeline while it implies agent delegation or behavior beyond the
one-call/one-answer contract.

Aliases can drift. A ledger should record both the requested alias and the
provider-resolved model identifier whenever the transport exposes it.

## 10. Caching is an experiment, not an assumption

Caching was one of the largest recovered Claude wins, so a Codex profile must
not quietly discard it. It also must not report success merely because the same
prompt was sent twice.

The Codex cache protocol should run at least four small probes using one real
rung shape:

1. cold call;
2. immediate byte-identical repeat;
3. delayed byte-identical repeat;
4. stable instructions with changed fact payload.

For each, retain raw CLI events, input/output/reasoning tokens, any cached-input
metric, resolved model, latency, exit status, and final content. The experiment
must answer:

- whether the stable instruction prefix is actually reused;
- which configuration or harness sections precede it and invalidate reuse;
- whether schemas participate in the cache key;
- whether a changed fact payload preserves a stable-prefix benefit;
- how long useful reuse survives;
- whether subscription usage reports enough detail to enforce a meaningful
  cache regression predicate.

Until those measurements exist, the profile's cache capability is `unknown`,
not `passing` or `failing`. Cache audit logic should branch on declared provider
capabilities: require the proven metric when observable, and state "not
observable" prominently when it is not. It must never turn missing telemetry
into a fabricated cache hit.

## 11. Usage, cost, and exit reporting

`InvokeResult` should expose a provider-neutral core while retaining the raw
provider envelope or normalized provider extras:

```text
final text
provider/session/call identifiers
requested and resolved model
requested effort
input, cached-input, output, and reasoning tokens when observable
measured or calculated API-equivalent cost, with basis
wall and provider latency when observable
stop reason and exit status
structured-output enforcement mode
transport retry and throttle history
isolation/profile version
```

The Run Report must stop making a global Claude claim. Its note should be built
from the calls actually present and distinguish:

- subscription usage with a provider-reported API-equivalent value;
- subscription usage with a locally calculated reference value;
- directly billed API cost;
- metrics the transport does not expose.

Calculated cost is valuable for comparison but must be labeled calculated. A
zero or absent dollar amount must never be interpreted as zero usage. The exit
report continues to include acceptance/repair rates, disagreement, validation
failures, cache behavior, latency, output density, learning-channel consumers,
and deterministic migration recommendations.

## 12. Rung names and stored history

The engine already treats rungs as work categories, but some stored state and
human wording still encode Claude-era names. That creates conceptual debt once
another provider runs the same rung.

The initial provider implementation should not rewrite historical states or
perform a risky store migration. It should:

- display provider-neutral labels such as bulk, escalated, and residue;
- record the actual source, model, and effort beside each transition;
- preserve existing stored identifiers for compatibility;
- define a later, explicit migration if the persisted vocabulary itself must be
  made provider-neutral.

This keeps provider enablement contained and makes history intelligible without
conflating a naming cleanup with transport correctness.

## 13. Research and validation program

### Stage A: zero-cost contract work

1. Freeze the profile schema and resolution precedence.
2. Capture representative Codex JSONL fixtures for success, invalid contract,
   auth expiry, rate limit, timeout, interrupted execution, and a provider error
   after partial events.
3. Build parser tests that preserve paid output and diagnostics on every
   recoverable failure.
4. Prove the isolation argv/config with subprocess seam tests.
5. Make accounting and Run Report wording provider-neutral.
6. Prove existing Claude behavior is byte- and ledger-compatible when selected
   through `claude-max`.

### Stage B: minimal live probes

1. Authentication and one-answer smoke test.
2. Tool/isolation negative probe.
3. Output-schema negative probe: deliberately violate the schema and confirm
   whether final output, JSONL, usage, and exit status remain recoverable.
4. Four-call cache protocol from section 10.
5. Throttle/concurrency observation with only enough parallelism to expose the
   subscription behavior.

These probes should be small but should not use a hard ceiling so tight that a
single complete answer is cut off. The run-level pause/checkpoint remains the
runaway guard.

### Stage C: same-corpus canary

Run the existing bounded polyglot canary through `claude-max` and
`chatgpt-pro`, preserving the full ledgers and exit reports. Compare:

- grounded target coverage and target conservation;
- evidence validity and unsupported-claim rate;
- adjudicator disagreement;
- gap and identity detection;
- escalation and repair behavior;
- final synthesis and determination usefulness;
- learning-channel completeness and named consumers;
- output density and discarded-output rate;
- input, cached input, reasoning, and output usage;
- latency, retries, throttles, and incomplete calls;
- deterministic recommendations found by each run.

### Stage D: real repository gate

Only after Stage C passes, run one UnaMentis partition with the ChatGPT profile,
then a second meaningfully different partition. A clean first partition is not
enough if the second exercises a different language, component shape, or
escalation path.

## 14. Acceptance gates

The ChatGPT Pro profile is ready for a full repository only when all of these
are true:

- no unaccounted tool use, repository reads, or hidden multi-turn behavior;
- zero lost successful responses, including schema and transport failure paths;
- all existing deterministic schema, byte, target, store-census, and audit
  gates pass;
- no material quality regression against the Claude control canary;
- adjudication, escalation, and repair retain their intended independence and
  semantics;
- the exit report contains enough data to diagnose the run and recommend
  deterministic improvements;
- usage accounting is honest about measured, calculated, and unavailable data;
- cache behavior is measured and its audit predicate matches what the provider
  can actually expose;
- cancellation or pause stops new launches, preserves completed work, and can
  resume without re-spending accepted work;
- the resolved profile and per-call provider/model/effort are auditable.

Efficiency improvements are evaluated only after the quality and learning
gates pass. There is no acceptance path based on sacrificing a small amount of
quality for a large usage reduction.

## 15. Proposed implementation slices

1. **Transport:** add `CodexCliInvoker` and register a distinct Codex CLI source.
2. **Profiles:** add immutable named profiles and `--ai-profile`; preserve
   `--phase-model` as a post-profile override.
3. **Isolation:** create and test the minimal Codex execution config and fixed
   working directory.
4. **Envelope:** parse JSONL, capture the final-output file, normalize errors,
   and preserve raw diagnostics.
5. **Accounting:** generalize ledger and Run Report cost/usage wording.
6. **Capabilities:** make cache, structured output, cost, and token visibility
   explicit provider capabilities rather than Claude-shaped assumptions.
7. **Fixtures:** add real subprocess fixtures for every named failure class.
8. **Live proof:** run isolation, schema, cache, and concurrency probes.
9. **Canary:** execute and compare the same bounded corpus across profiles.
10. **Real proof:** execute two diverse UnaMentis partitions before authorizing
    a full ChatGPT-backed run.

The first four slices establish correctness. The next three establish honest
observability. The final three establish real-provider behavior and quality.

## 16. Effort and usage estimate

When resumed, the expected engineering shape is:

| Work | Estimate |
|---|---:|
| Basic Codex transport and JSONL parsing | 3-5 hours |
| Profile resolution, CLI, isolation, and tests | 4-7 hours |
| Provider-neutral accounting/reporting and capability gates | 3-5 hours |
| Live probes and fixes | 3-5 hours |
| Cross-provider canary and evaluation | 2-4 hours |
| **Trustworthy total** | **1.5-2.5 focused days** |

The small live protocol is expected to consume only a modest amount of
subscription capacity; an API-equivalent reference band of roughly $5 to $15
is sufficient for planning, not a hard stop and not necessarily cash billed.
The actual subscription usage must be reported from the live envelopes to the
extent each CLI exposes it.

## 17. Later API-backed operating model

Direct APIs are intentionally out of the present scope. They become the likely
default when Solution Explorer runs enrichment for customers or is licensed for
customers to operate themselves.

That phase should add profiles such as `anthropic-api` and `openai-api` behind
the same contract, then address the operational concerns that local subscription
CLIs do not solve:

- tenant and credential isolation;
- secrets rotation and revocation;
- pinned model/version policy and controlled upgrades;
- explicit pricing, budgets, billing, and pass-through attribution;
- rate-limit and capacity planning;
- data retention, regional processing, and organization policy;
- audit logs and customer-visible run provenance;
- service-level retry, queueing, cancellation, and resume;
- provider outage and failover policy;
- evaluation gates for any automatic provider routing.

The subscription-backed profile work should avoid blocking this future, but it
should not implement those operational systems prematurely.

## 18. Open questions to settle experimentally

- Which Codex settings are sufficient to exclude all ambient user/project
  context while retaining ChatGPT authentication?
- What exact usage and cached-token fields appear in current `codex exec --json`
  events for subscription-backed calls?
- Does `--output-schema` preserve a failed response and full usage diagnostics,
  or can it turn paid work into an opaque failure?
- What stable-prefix cache behavior is observable through Codex CLI, and which
  harness instructions participate in its key?
- What concurrency level avoids subscription throttling without serializing the
  pipeline unnecessarily?
- Which model and effort combinations achieve quality parity per rung?
- Can provider-independent adjudication materially improve the disagreement
  signal enough to justify a hybrid profile?

None of these questions blocks the current Claude Max path. All of them block a
claim that ChatGPT Pro is production-equivalent.

## 19. Re-entry checklist

When this work is picked up:

1. Re-read this plan and the current enrichment economics reports.
2. Re-check the installed Claude and Codex CLI versions, authentication modes,
   model catalogs, and official configuration documentation; they are
   time-sensitive.
3. Re-audit the provider seam because the enrichment engine may have evolved.
4. Convert the staged program into a short implementation branch and record
   every live probe beside its raw envelopes.
5. Stop after the same-corpus canary for a cross-review before enabling a full
   ChatGPT-backed repository run.

## 20. Reference material

Repository sources:

- [Enrichment Engine](../../publication/ENRICHMENT-ENGINE.md)
- [Enrichment economics engagement report](ENGAGEMENT-REPORT-2026-08-26.md)
- [Orchestration specification](ORCHESTRATION-SPEC.md)
- [Prompt specification](PROMPT-SPEC.md)
- [Post-unification canary report](POST-UNIFICATION-CANARY-REPORT-2026-08-27.md)
- [Remediation task tracker](../../remediation/TASKS.md)

Current official OpenAI references, to be rechecked at implementation time:

- [Codex CLI developer commands](https://learn.chatgpt.com/docs/developer-commands?surface=cli)
- [Codex authentication](https://learn.chatgpt.com/docs/auth)
- [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [OpenAI model selection guidance](https://developers.openai.com/api/docs/guides/latest-model)
