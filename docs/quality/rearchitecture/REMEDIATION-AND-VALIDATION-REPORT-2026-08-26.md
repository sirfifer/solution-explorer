# Remediation and validation report: enrichment economics

Date: 2026-08-26 (US/Pacific)

Branch reviewed and changed: `deterministic-gate-hardening`

Starting commit: `e1dbb70`
Validation subject: the 8-component, 1-relationship polyglot fixture

## Executive verdict

The deterministic implementation is substantially stronger and the complete
repository suite is green. The redesign's P2 output economics also passed its
narrow measured gates on the live fixture.

The release verdict remains **STOP for a full UnaMentis or VS Code run**. The
latest full live fixture run did not meet the quality gate, exceeded its stated
dollar ceiling, and exposed a changing P5 cache prefix. Those failures are now
reported truthfully and their deterministic causes have been remediated, but the
remediated code has not been re-proven by another paid end-to-end run. A green
test suite is not a substitute for that production-boundary gate.

## What this pass changed

### Transport, ceilings, and completion truth

- Removed the CLI's payload-destroying `--json-schema` boundary from compact
  calls. Compact JSON is parsed, schema-checked, normalized, and coverage-checked
  in process, so a cosmetic alias can be stripped while a real shape error is
  rejected without erasing the whole batch.
- Preserved session identifiers and recoverable usage/cost from nonzero CLI
  envelopes.
- Added per-phase delivered-byte budgets and made any violation a failed call.
- Added run-level cost reservations and passed the remaining allowance through
  the CLI. The implementation and report now state the observed limitation
  honestly: Claude CLI `--max-budget-usd` is not a hard single-response cap.
- Added an explicit `cost-ceiling-overshoot` audit failure and publication
  failure. An overspent run cannot report complete even if every phase returned.
- Split operational success from publication quality. Completion requires a
  `done` determination, every criterion met, measured adjudication at or below
  20%, no failed calls, all byte budgets satisfied, and an audit pass.

### Grounding quality

- Expanded the deterministic fact vocabulary to include exact files, edges,
  configuration manifests and their parsed values, documentation excerpts,
  system relationship/capability counts, capability-bearing component count,
  and system-wide maximum inbound/outbound counts.
- Added deterministic citations when a claim names those exact facts. Global
  facts are marked global; a local count still cannot prove a system-wide
  uniqueness claim.
- Kept evidence existence separate from semantic sufficiency. The validator can
  prove that a cited fact exists; P3 still decides whether the fact actually
  carries every clause of the claim.
- Re-runs scoped P3 grounding and substitution checks after an executed repair
  order, replacing the old verdicts for those targets.
- Work orders now receive P3's exact rejected question, claim, citations, and
  rejection reason. Previously P5 saw those failures but the descended repair
  tier received only “apply the lens,” paid to rediscover the problem, and often
  changed nothing.
- A work order cannot demote a grounded contract state. P5 is also forbidden
  from issuing enrichment work orders that claim they can change parser facts or
  independent identity/edge/finding verifier verdicts.

### Output and cache economics

- Compact components and relationships use separate calls, exact target-set
  conservation, bounded arrays/strings, evidence-menu references, and a
  single-source semantic atom reused by product prose and the contract.
- Escalations and work orders emit only named deltas; settled answers remain in
  the store and are not re-emitted.
- Work-order assignments, P5 census, adjudication, budget, and round history are
  now in uncached user tails. Instructions, criteria, brief, and synthesis stay
  in byte-stable prefixes.
- The audit now detects two different cold singleton P5/work-order prefixes.
  The earlier per-hash rule could call both locally healthy and miss the fact
  that changing run data had fragmented the stable contract.
- The measured bulk density gate is 430 billed output tokens per target. This is
  2.2% above the quality-complete fixture measurement of 420.8 and 67.7% below
  the 1,332-token baseline. The ladder and escalation gates remain 500 per
  unique target and 260 per escalated attempt.

## Deterministic verification

Final repository-wide test run:

- **2,236 passed**
- **4 skipped**
- **1 expected failure**
- **0 failed**
- Runtime: 155.76 seconds

Ruff passes over every changed production, script, and test file. `git diff
--check` also passes. The committed reference report was regenerated only via
its environment-gated fixture test and then independently re-verified.

New or strengthened tests cover the real transport argv/envelope seam,
in-process schema handling, exact coverage and duplicate rejection, fact
vocabulary conformance, global/local scope, cache prefix stability, cost
overshoot, publication completion, no-demotion, scoped adjudication handoff, and
the full scripted pipeline.

## Latest live fixture evidence

The preserved historical run is under
`data/remediation-final-2026-08-26/`. It is the pre-remediation run that exposed
the remaining defects; it is not represented as a passing run. Raw provider
transcripts and the 51 MB scratch database are not copied.

### Economics

| Measure | Observed | Gate | Result |
|---|---:|---:|---|
| Planned/final P2 targets | 9 / 9 | exact equality | pass |
| 2a output density | 420.8 tokens/target | <= 430 | pass |
| Whole ladder output density | 470.1 tokens/target | <= 500 | pass |
| Escalation output density | 148.0 tokens/attempt | <= 260 | pass |
| Delivered-byte violations | 0 | 0 | pass |
| All-phase billed output | 17,693 tokens | learning-output gate only | measured |
| All-phase output per target | 1,965.9 tokens | no certified large-run gate | measured |
| Measured cost | $2.721914 | $2.500000 | **fail, +8.9%** |

P2 grounded all nine targets: the cheap rung carried the normal component and
relationship batches, and three component repairs went to Opus. The final
census had seven Sonnet and two Opus targets. No Fable escalation was needed in
P2.

The full-run number is much larger than the P2 density because P1, P3, P4, P5,
and one work-order/recheck round are fixed or weakly amortized on a nine-target
fixture. It must not be hidden by quoting only the ladder.

### Quality

P3 rejected 14 of 18 scoped claims after the repair round: **77.8%
disagreement**, against a 20% completion ceiling. This is a real quality
failure, not a validator nuisance.

The failure analysis separated missing evidence from false breadth:

- Newly exposed exact line/file counts, parsed compose services/ports,
  documentation, manifest paths, exact edges, global capability counts, and
  global maximum edge counts can carry most rejected clauses directly.
- One representative claim said both `client.ts` and `format.js` implemented
  HTTP request logic. The analyzer established the two files and the HTTP edge,
  but not that both files implement that behavior. The correct repair is to
  narrow the sentence, not attach a more impressive citation.

The work-order handoff now supplies those exact P3 failures to the repair tier.
This change removes the blind rework seen in the preserved run, but its live
resolution rate remains unmeasured until the next bounded pilot.

### Caching

The live ladder rows satisfied their prefix-read floors and had no non-warm
zero-read cache misses. The run nevertheless rendered two P5 prefix hashes
because changing adjudication was still in the prefix. The strengthened audit
now reports one stable-prefix fragmentation, and the code now places
adjudication in the changing tail. Work-order assignment text was moved to that
tail for the same reason.

### Why the cost ceiling is not “hard” on this transport

The last P5 call received a $0.210893 reservation and returned a measured
$0.432808 cost. The engine failed the call and the audit fails the run, which is
honest post-delivery enforcement, but the billing had already happened.

Therefore:

- delivered JSON bytes, schema, item counts, target ids, and store conservation
  are deterministic gates;
- billed output density and measured dollars are deterministic after delivery;
- a 100% preventative billed-token/dollar ceiling requires a transport with a
  server-side output-token limit (for example a direct API `max_tokens`-style
  control). Claude CLI does not currently provide that guarantee.

## Current zero-cost projections on the real stores

The replay planner was run again on this exact code state. Both stores pass:
one byte-stable prefix per target kind, every call under the output-dispersion
projection, and every prompt under the context warning bound.

| Subject | Components | Relationships | Planned 2a calls | Projected 2a billed output |
|---|---:|---:|---:|---:|
| UnaMentis iOS | 168 | 458 | 32 (14 component, 18 relationship) | 179,062 tokens |
| VS Code | 569 | 5,453 | 231 (61 component, 170 relationship) | 1,146,472 tokens |

The prior cost model's conditional ladder bands remain approximately **$10-$23
for UnaMentis** and **$67-$147 for VS Code**. They are workload arithmetic, not
authorization estimates. The current meta phases and repair-resolution rate do
not yet have a successful live calibration, so a defensible total price cannot
be certified. It must be recomputed from the next green pilot's Sonnet
acceptance, escalation, cache reads, P3 sample sizes, and work-order rounds.

## Migration and cutover

No database migration was performed or is needed for this remediation. The
ladder performs a full target pass and overwrites its component, relationship,
and contract-state rows through the same provenance-stamped store API. Legacy
compact and canonical response shapes remain readable by the normalizer.

The legacy single-pass enhance route remains the default; the redesigned ladder
still requires `--ladder`. Promoting it to the default would be a cutover, not a
data migration, and is intentionally blocked on a green bounded live gate.
Silently changing the default now would turn an unproven path into production.

## Spend record

- This remediation pass after the independent report: approximately **$6.653**
  API-equivalent ($3.543003 first full attempt, $2.721914 second full attempt,
  and about $0.388 in bounded component/transport probes).
- Earlier unified-session cache probes: **$1.48**.
- Earlier independent pilot: **$2.1505**.
- Documented cumulative live work across those stages: approximately
  **$10.28 API-equivalent**.

No paid model call was made after the final deterministic repairs in this
report. That is deliberate: the failed full fixture run already identified the
defects, and repeating it before closing them would only have bought the same
finding twice.

## Required next gate

The next reviewing session should begin from the committed diff and the
preserved run, then independently verify the following before any full corpus:

1. Review the exact code changes and rerun the complete suite.
2. Run one bounded full polyglot pipeline with one improvement round. Required:
   zero failed calls, exact census, no byte violations, one P5 prefix hash,
   adjudication disagreement <=20%, every criterion met, final `done`, audit
   pass, and measured cost reported honestly.
3. Decide explicitly whether to adopt a direct API transport for a preventative
   token/cost ceiling. If the CLI remains, documentation and automation must
   continue to call the dollar limit a best-effort launch allowance with a
   post-run violation gate.
4. Only after step 2 is green, run one UnaMentis partition and then two. Recompute
   the subject projection from those measurements.
5. Keep trigger-class routing activation behind its M-R1 replay and keep the
   ladder opt-in until the release gate passes.

That sequence preserves the central rule of this engagement: efficiency work
does not buy permission to lower quality, and deterministic checks do not claim
to prove what only a bounded production call can establish.
