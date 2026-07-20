# Robustness strategy: gating, self-validation, and resilience

Matured 2026-07-20 from two research briefings plus owner direction. This is the
"how we build safely at speed" authority. Its companion is
REGRESSION-STRATEGY.md ("how we prove we did not regress"). Both exist to serve
the two ethics already canonical in VISION.md: 100 percent accounting is the
only mode, and no theater (a fractured or half-built result presented as
complete is theater; an honest gap is truth).

The through-line for everything below: the coverage ledger's guarantee, every
file accounted for exactly once, is an output postcondition. This document
generalizes that one proven idea to every tier and every feature. A piece of
functionality that cannot produce a whole, well-formed result must record an
honest gap, never ship a fracture and never crash the run.

## The two paradigms (this reframes everything)

The analyzer runs in two very different regimes, and a pattern that is overkill
in one can be essential in the other.

- PARADIGM A, the initial full pass. A short-lived, mostly single-process batch
  run over an entire codebase. State does not persist across calls. The failures
  that matter are an exception in one unit crashing the whole run, and a
  producer shipping incomplete output. Runtime service patterns (in-process
  circuit breakers, resource-pool bulkheads, liveness endpoints) do NOT transfer
  here; they are ceremony.

- PARADIGM B, the auto-update on merge. On a merge to the configured target
  branch the pipeline regenerates (analyze, derive, project, AI-enrich, deploy).
  For a solo or small operator this fires rarely and behaves like Paradigm A.
  For a full-time team of 10 to 30 it fires dozens of times a day. In aggregate
  that is service-like even though each run is a fresh process: a single broken
  pass fails dozens of times a day, burning CI minutes, burning real AI-API
  money on every run, and shipping degraded artifacts repeatedly. This paradigm
  pulls SOME service patterns back in, with a specific nuance (see Circuit
  breaker below): the state that a breaker needs must be PERSISTED across runs,
  not held in-process.

The batch-vs-service split, in one line: timeouts, bounded retry with full
jitter, output-contract validation, per-unit exception isolation, graceful
degradation, and honest-gap recording all apply to both paradigms. In-process
circuit breakers and resource-pool bulkheads apply to neither batch run; a
PERSISTED cross-run breaker applies to Paradigm B at team scale and to the MCP
server, which is the one genuinely long-running service.

## Maturity gating (readiness), not boolean flags

The industry has settled on trunk-based development plus gating over long-lived
branches; a v1-maintenance / v2-development branch split is the merge-debt trap
for a solo dev and is already rejected in our practice (short-lived worktrees,
same-day merges). The disciplined gating model is the Kubernetes / Rust maturity
model, not a SaaS feature-flag platform:

- Each gateable feature declares a stability: experimental, beta, or stable.
- A resolved channel (default: stable) decides what is active. Experimental is
  OFF by default and explicitly labeled, which is the no-theater rule expressed
  as release management: an alpha feature that says it is alpha is honest; a
  half-built feature that looks done is theater.
- In-repo and server-free. No SaaS dependency, no running flag server (a
  documented overkill below team scale, and a hard-resource cost we avoid).
  Analyzer side: a small features module resolving a channel from an env var or
  a --channel flag. Viewer side: genuinely-unfinished features use a build-time
  constant so the bundler dead-code-eliminates them (invisible to users and
  bots, zero cost); alpha features you want to exercise use a URL-param override
  (labeled experimental). Lenses and panels already register, so each just
  declares its maturity.
- Determinism is preserved: an experimental analyzer feature that is off must be
  a true no-op, so a default run stays byte-identical, and the active gates get
  stamped into the projection provenance so any non-default output is
  self-explaining. This is the Rust guarantee (unstable code cannot activate in
  a stable build).
- Governance is the load-bearing part. Stale gates are the number-one documented
  failure mode, and a solo dev at AI velocity is maximally exposed. Every gate
  carries a maturity, an owner, and a graduation-or-removal expectation recorded
  in TASKS.md. The recurring dogfood gate reviews the gate inventory and forces
  each stale one to graduate or die. Fowler's rule verbatim: a feature is not
  done until its release gate is archived.

Prefer the keystone pattern to a gate when possible: build a feature fully but
wire the last user-visible connection in the final small commit, so it is dark
until it works, with no gate machinery at all. Reach for a gate only when a
feature must be partially visible before it is done.

## Self-validating output (the backbone)

The pattern is Design by Contract (Meyer): postconditions and invariants,
plus fail-fast. The specific level is shape-and-completeness validation, not
value validation. Each producer (each derive pass, each emitter, each MCP tool,
each enrichment pass) asserts the postconditions that describe a whole,
well-formed artifact, and deliberately does not assert the content of individual
values. The owner's canonical example: a producer that should emit three
categories of data and is about to hand off a result with one must be stopped at
runtime, at handoff time, not later.

- Tooling: Pydantic v2 for the output model (validates the result and emits the
  JSON Schema we feed the AI API's response_format, so the model is constrained
  at generation and re-validated after, from one definition). A shared .json
  schema is the contract between the Python analyzer and the JS viewer.
- The discipline that keeps it lightweight: assert presence, shape, count
  consistency, and cross-reference resolution; never assert what a value is.
  Validation creep toward content checks is the failure mode; it is slow,
  brittle, and quietly re-implements the logic being validated. If a check
  asserts what a value is rather than that the required things are present and
  consistent, it has gone too far.
- On failure: record an honest gap (a ledger entry: this producer could not
  produce a complete result, here is why), never ship the fracture. The gap is
  deterministic (same input, same gap) so parity holds.

## Fault isolation

Architecture: a modular monolith, which the 2026 consensus names as the right
default below roughly 15 developers (microservices there are a net productivity
loss). One deployable, strict in-code module boundaries, no shared mutable
state, which the analyzer already approximates (independent derive passes,
per-language parsers, a lens registry).

- Bulkhead intent for a batch pipeline is per-unit exception isolation: the
  driver wraps each pass in its own try/except so a failing pass degrades to an
  honest gap instead of aborting the run. The registry/plugin pattern is the
  structural expression (each pass is an independent unit invoked in a loop).
- Process isolation is the heavy option and we already use it for the right
  reason: ProcessPoolExecutor contains native tree-sitter crashes that a Python
  try/except cannot catch (a segfault would take down an in-process run). Reserve
  it for units that call native code.

## Retry, timeout, and the runaway defense

- Exponential backoff WITH jitter (full jitter) for transient failures only.
  Jitter is the part that matters; plain backoff still clusters. Retry only
  transient errors (429, 5xx, timeouts, resets); never retry deterministic ones
  (4xx, schema violations, parse failures), which fail identically every time.
- The one surface in the batch pipeline that needs this is the outbound AI-model
  call. Parse failures are deterministic and must fail fast and be recorded, as
  they already do. P4-8 in-run retry already classifies transient vs
  deterministic and rebuilds a dead worker pool; the AI-call path should get the
  same treatment.
- Tooling: stamina (opinionated wrapper over tenacity, ships the right defaults:
  transient-only, jitter, bounded attempts and total time) is the recommended
  default; drop to raw tenacity only for custom composition.
- The timeout is the primary runaway defense and the most underrated pattern.
  Every outbound call needs a per-attempt timeout, plus a total-time budget, so
  no single call can wedge a run.

## Circuit breaker (be precise about where)

States: closed, open, half-open (open after a trip threshold, half-open probes
recovery after a cooldown and auto-reenables). It needs state that accumulates
across many calls.

- The initial full pass (Paradigm A): overkill. A short-lived run accumulates no
  such state; bounded retries plus a timeout already prevent a single-run
  runaway. Do not add one.
- The auto-update pipeline at team scale (Paradigm B): justified, but the
  in-process breaker still does not fit because each run is fresh. The correct
  form is a PERSISTED, cross-run breaker whose state lives in the store or a
  small status artifact: after a pass fails its output contract on N consecutive
  auto-update runs, auto-disable that expensive pass (especially AI enrichment),
  alert a human, keep shipping the rest, and auto-reenable on a fix or a manual
  clear. Pair with a hard per-run cost ceiling on the AI pass so a flaky
  dependency cannot burn unbounded money across a day of merges.
- The MCP server: the one genuinely long-running service; a conventional
  in-process breaker (pybreaker sync, or purgatory async with a persistent
  backend) around its outbound dependencies is appropriate when it is hardened
  for real use.

## Health signals and honest gaps

For the batch tiers, the honest-gap record in the artifact IS the health signal:
a failed pass writes an explicit "produced nothing, here is why" entry that the
ledger accounts for and the viewer degrades around. Structured logging
(structlog, JSON, sub-1 percent overhead) is the lightweight observability, no
APM stack. The MCP server additionally gets a liveness endpoint.

## The parity contract (incremental equals full)

The property that makes light-handed auto-update valid is that an incremental
auto-update produces the same result as a full regeneration. This is already a
tested invariant at the extract and derive tiers (a warm incremental store is
byte-identical to a cold full run). It must be guaranteed end to end, including
the enrichment tier (enhance --update plus the drift-tolerant merge). This is a
first-class contract: if it holds, nobody needs to regenerate fully every day,
because the only value in doing so is catching things that slipped through
cracks, which is the exact thing the tool exists to prevent. The per-commit
byte-parity tests prove it on fixtures; the periodic full-regeneration-and-diff
on a frozen real-world corpus (see REGRESSION-STRATEGY.md) proves it on real
data at scale. Both check the same contract at different altitudes.

## What already exists (formalize, do not bolt on)

- Coverage ledger completeness = an output postcondition, tested.
- P4-8 in-run retry = transient-vs-deterministic retry plus a miniature pool
  rebuild.
- Enrichment quality gate (score threshold, PASS/FAIL before stamping) =
  self-validating output before handoff.
- Additive projection plus viewer degradation = graceful degradation, required.
- ProcessPoolExecutor = process isolation for native crashes.
- Provenance digests = contract stamping.
- Full-vs-incremental byte parity = the parity contract, at two tiers.

## What NOT to do

No microservices. No long-lived v1/v2 branches. No SaaS flag or breaker
platform, no running flag server (overkill below team scale, and a hard-resource
cost). No in-process circuit breaker in the batch tool. No content-level
validation creep (hold at shape-and-completeness). No gate left to accumulate as
permanent config.

## Candidate cards (design here, owner green-lights builds)

- R1: the output-contract plus honest-gap backbone. Generalize the coverage
  ledger's completeness guarantee to every producer via Pydantic v2 output
  models and completeness postconditions, with per-unit exception isolation in
  the driver. Highest value, most on-brand.
- R2: stamina-based retry with jitter and a per-attempt timeout plus cost
  ceiling on the AI-enrichment call path. Formalizes P4-8's lesson for the
  external-API surface.
- R3: the maturity-channel gating system (analyzer features module, viewer
  build-time-constant plus URL-param, provenance stamping, governance in the
  dogfood gate).
- R4 (Paradigm B): the persisted cross-run breaker plus cost ceiling for the
  auto-update pipeline, and the conventional breaker plus liveness for the MCP
  server, when each is hardened for real use.
