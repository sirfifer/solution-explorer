# Global one-hour caching was a cost bug; selective five-minute caching helps

Subject: the Claude CLI enhancement pipeline, evaluated against the completed
UnaMentis iOS run and a fresh disposable UnaMentis partition on 2026-08-31.
Code under test was the uncommitted cache-policy and quality-hardening change
set on `deterministic-gate-hardening`. All dollar figures are API-equivalent
prices reported by the CLI; the calls used the owner's Claude subscription and
did not create an API bill.

## Decision

Keep prompt caching. Do not use it globally.

The default policy is now `adaptive`:

- use a five-minute cache only for repeated, prefix-stable verification and
  improvement phases;
- turn caching off for orientation, bulk enrichment, escalation, narrative,
  spine, and independent edge/finding verification, whose large facts payloads
  are unique or whose repetition was not demonstrated;
- never choose the one-hour cache automatically;
- retain explicit `off`, `5m`, `1h`, and provider-default controls for probes
  and future evidence-driven policy changes.

The cache-policy change itself is not a quality/cost trade. Anthropic states
that prompt caching reuses an identical processed prefix and does not change
the generated response. The quality contract, evidence requirements,
adjudication, learning record, and exit analysis remain in force. That policy
changes how identical input is charged and processed, not what the model
receives. This change set also contains separately described prompt and
deterministic-derivation corrections that do change the information available
to the model and the facts entering enhancement.

## Why the earlier conclusions both contained part of the truth

The early 126k-token ladder said the cache returned little. That observation
was real, but it was not a valid basis for deleting the mechanism: the dynamic
system prompt was breaking prefix identity, and one-hour automatic writes were
charging a premium on large per-call facts that were never read again.

The later mechanism probe proved that a stable prefix can produce 81–90%
repeat-call reductions. That was also real, but it did not prove that caching
the entire full-run workload was economical. The completed UnaMentis ledger
finally supplied the missing workload-shape evidence.

Both results reconcile under one rule: **cache a stable prefix only when enough
later calls reuse it before expiry to repay its write premium.**

Anthropic's current documented multipliers are:

| operation | base-input equivalent |
|---|---:|
| uncached input | 1.00x |
| five-minute cache write | 1.25x |
| one-hour cache write | 2.00x |
| cache read | 0.10x |

Source: [Anthropic prompt-caching documentation](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
and [Anthropic pricing documentation](https://platform.claude.com/docs/en/about-claude/pricing).
The documentation also says cache hits require a byte-identical prompt prefix.

For a cached region with write volume `W` and later reads `R`, the comparison
against processing those tokens normally is now computed exactly:

```text
five-minute actual = 1.25W + 0.10R
one-hour actual     = 2.00W + 0.10R
uncached comparison = W + R
```

A negative difference is a saving. A positive difference is a cost. Unknown
write TTL makes the result unknown rather than letting the report invent a
saving from reads alone.

## What the completed UnaMentis run says

The 2026-08-30 ledger records 5,387,974 cache-write tokens, 1,359,061
cache-read tokens, and 544 fresh input tokens: 0.252 reads per written token.
It did not record write TTL per row. The run configuration and the close fit
to the CLI's metered total establish that those writes used the then-global
one-hour policy, but that TTL is a reconstruction rather than a ledger field.

There are three valid comparisons, and they answer different questions:

| basis | one-hour actual | uncached comparison | penalty |
|---|---:|---:|---:|
| model-independent input equivalents | 10,912,398 | 6,747,579 | **61.7%** |
| model-weighted published input prices | $45.82 | $29.10 | **57.4%** |
| published prices including unchanged output | $55.32 | $38.60 | **$16.72 / 43.3%** |

The CLI metered $58.92 for the historical run. That is a distinct provider
metering basis, not the denominator for the 43.3% figure. The $55.32 published-
price reconstruction is within 6.5% of it, which is additional evidence for
the one-hour classification. Repricing the same ledger globally at five
minutes gives $38.38 including output; it would avoid the large one-hour
premium but still cache phases that do not repay even a five-minute write.

The adaptive projection is $36.94 on the same published-price basis. Turning
off the global one-hour policy recovers about $16.72, and selective five-minute
caching adds about $1.66 more. Combined, the policy correction projects a
$18.37 reduction, or 33.2% of the old modeled total. The single-digit adaptive
gain is therefore an optimization on top of the much larger one-hour-policy
bug fix, not the headline result by itself.

The cache mechanism worked. The global one-hour policy was wrong. Its write
premium needed more than one read per written token and the workload returned
only one quarter of a read.

Replaying the same rows as five-minute writes showed why a global switch still
would not be the right answer. Some phases save and others lose:

| phase family | projected five-minute net, base-input equivalents | choice |
|---|---:|---|
| bulk rung 2a | +280,495 | off |
| Opus escalation | +49,091 | off |
| orientation | +3,669 | off |
| narrative | +2,954 | off |
| synthesis spine | +8,518 | off |
| verify edges | +17,757 | off |
| verify findings | +7,944 | off |
| P5 work orders | -16,929 | 5m |
| grounding checks | -40,320 | 5m |
| P5 determination | -84,676 | 5m |
| substitution checks | -104,670 | 5m |
| identity checks | -6,898 | 5m |

Positive values cost more than uncached processing; negative values save.
These are ledger projections, used to choose the policy before spending on the
integrated canary.

## Controlled live probe: mechanism evidence

`scripts/cache-policy-probe.py` runs identical real-store prompts under three
cache arms and records raw provider usage, TTL classes, contract validity, and
exact economics. Four calls per arm on one real UnaMentis component produced:

| policy | write | read | actual input equivalent | vs uncached | API-equiv |
|---|---:|---:|---:|---:|---:|
| off | 0 | 0 | 97,950.0 | baseline | $0.376974 |
| 5m | 66,701 | 31,245 | 86,508.8 | **11.68% saving** | $0.337896 |
| 1h | 66,701 | 31,245 | 136,534.5 | **39.39% loss** | $0.480974 |

All 12 provider calls completed. The first prompt version allowed the model to
render optional assessment strings as structured objects, so three arms were
not a clean quality comparison even though they were a valid mechanism and
economics comparison. The prompt contract was made explicit, then the 5m arm
was rerun twice: 2/2 provider calls and 2/2 contracts passed, with a 14.77%
input-equivalent saving. The invalid first outputs were not hidden or counted
as success.

## Integrated one-partition canary: workload evidence

A disposable copy of the full UnaMentis store then ran one complete partition,
including orientation, the ladder, verification, adjudication, improvement,
synthesis, and determination:

- 68 contract targets;
- 112 model calls, all successful;
- 0 retries and 0 compact-transport budget violations;
- $12.356671 API-equivalent;
- 584,868 fresh input, 879,714 five-minute writes, 429,287 reads, and
  108,108 billed output tokens;
- no one-hour or unknown-TTL writes;
- 1,727,439.2 actual input equivalents versus 1,893,869 uncached;
- **166,429.8 input equivalents saved, or 8.79% of uncached input volume**;
- using the calls' model-specific published rates, approximately **$0.98 saved,
  or 7.87% of the corresponding uncached run cost**.

The adaptive choices behaved as designed:

| cached family | calls | read/write | net saving, base-input equivalents |
|---|---:|---:|---:|
| P5 work orders | 11 | 0.379 | 25,458 |
| grounding checks | 48 | 0.440 | 52,603 |
| P5 determination | 4 | 0.760 | 40,205 |
| substitution checks | 35 | 0.713 | 47,565 |
| identity checks | 3 | 0.304 | 599 |

Identity checks are provisionally cached, not treated as strong evidence. In
this canary they wrote 25,778 tokens, read 7,826, and carried 6 fresh tokens:
33,011.1 actual input equivalents versus 33,610 uncached, a saving of only
598.9 equivalents (1.8%). That is close enough to break-even to flip with call
spacing. The completed ledger's ten identity calls project a 6,897.9-
equivalent five-minute saving, so the choice is consistent with the larger
workload but remains a phase to remeasure.

Every phase mapped to `off` recorded zero cache writes and reads. Most
importantly, the 21-target bulk call carried 242,713 fresh input tokens and did
not pay to cache that unique facts payload.

The 112-call canary is the primary workload evidence for the production phase
policy. The smaller controlled probe supplies causal transport evidence—that
the same prefix is written and then read under each requested TTL—but its
11.68% and 14.77% figures are too thin to headline as workload savings.

## What the quality canary discovered

The historical canary remains `NOT-DONE`. Its final report must not be edited
after the fact, and the audit correctly continues to fail it on criterion s6.
That failure led to five bounded quality fixes:

1. **Optional wire types.** The component prompt now says exactly which compact
   values are strings, preventing semantically adequate answers from failing a
   vague serialization contract.
2. **Compact evidence pairs.** A two-element compact citation such as
   `["S", "Symbol"]` is preserved as one citation rather than being flattened
   into two invalid evidence objects. Malformed raw evidence is retained for
   the learning record.
3. **Adjudication visibility.** P5 now receives bounded per-target verification
   outcomes, not merely aggregate counts, so it cannot repeatedly repair a
   claim an independent verifier has already refuted.
4. **Relationship context.** Relationship prompts include bounded declarations
   and references for both endpoints, giving a model the information needed to
   distinguish usage sites from definition sites.
5. **Swift same-name resolution.** The remaining s6 edge was not merely poorly
   explained; it was deterministically fabricated. The root app component and
   `core/knowledgebowl` both defined `KBQuestion`/`KBSessionSummary`. The deriver
   removed the local component from the candidate set first, making the other
   definition look uniquely external. Swift has no per-name import that could
   justify that choice. The deriver now treats this as local/ambiguous and emits
   no cross-component edge.

A focused live relationship call after adding endpoint context was contract
valid but still cited the root component's `Modules/KnowledgeBowl` usage sites.
That response was useful negative evidence: it showed that another prompt
iteration could not make the false deterministic edge true. Fixing the parser
was the quality-preserving answer.

Re-deriving the disposable UnaMentis index removed nine reciprocal same-name
Swift `uses` edges and added no new `uses` edges. The removed set includes the
exact `unamentis -> unamentis/core/knowledgebowl` edge that caused s6 to loop.
A regression test drives the real extract-and-derive path and freezes this
behavior.

## Implementation now in place

The change set supplies:

- CLI-wide `--cache-policy {adaptive,provider-default,5m,1h,off}` and repeatable
  `--phase-cache PHASE=POLICY` overrides;
- isolated child-process environment controls, so a parent shell's cache flags
  cannot silently override a run;
- explicit five-minute, one-hour, off, and provider-default engine behavior;
- nested TTL extraction from provider envelopes;
- a ledger row for the selected policy plus distinct 5m, 1h, and unknown write
  counts;
- per-policy exact economics in every exit report;
- audit gates that reject the wrong TTL, caching in an `off` phase, unknown-TTL
  accounting, or a policy claimed as a saving when its measured net is not
  negative;
- budget settlement based on actual cache economics rather than double-counted
  input totals;
- an operator control snapshot refreshed before reserve and settle operations;
- a reusable live three-arm cache probe;
- the quality and deterministic relationship fixes described above.

The report still preserves the information needed for continuous improvement:
fresh/write/read/output tokens, TTL, selected policy, prefix hash, phase, rung,
model, targets, cost, latency, retries, failures, response bytes, transport
budget result, escalation triggers, adjudication results, determination, and
parser findings. Efficiency did not delete the learning channel.

## Verification

Static verification:

- `git diff --check`: pass;
- Ruff across every changed Python file and test: pass.

Automated verification:

- **2,342 tests passed**;
- 4 tests intentionally skipped;
- 1 expected failure;
- 5 loopback HTTP tests initially could not bind a socket in the restricted
  sandbox, then passed 5/5 when rerun with local socket permission;
- no product or test failure remains.

Live validation spend for this engagement was approximately $13.77
API-equivalent: $1.195844 for the 12-call three-arm probe, $0.167663 for the
post-contract quality rerun, $12.356671 for the integrated partition, and
$0.049834 for the focused relationship diagnosis.

The audit of the already-completed canary reports 68/68 targets answered,
112/112 calls successful, exact net cache savings, and zero transport
violations. It still returns failure because the historical determination is
`not-done` and s6 is unmet. This is correct audit behavior, not a remaining
cache-policy failure.

## Readiness and boundaries

The cache decision is ready for the next large demo run: use `adaptive`. The
evidence is strong enough to reject both previous extremes—neither delete the
cache nor enable one-hour caching everywhere.

The next full run should not be expected to reproduce exactly 7.87% savings.
Savings depend on phase counts, prefix identity, call spacing, model mix, and
repair rate. The run is required to measure itself, and the audit will stop any
claim of benefit that its own ledger does not support.

Two boundaries remain deliberate:

- Claude Max exposes no documented conversion from API-equivalent cache prices
  to weekly subscription percentage. Account impact requires uncontaminated
  before/after `/usage` readings; the report does not fabricate that mapping.
- The Claude CLI controls the automatic breakpoint. A future direct API
  transport could place an explicit breakpoint after the stable instructions
  and before unique facts, which may improve the bulk rung. That is a provider
  transport improvement, not a reason to delay the proven adaptive policy.

Policy changes after the VS Code demo should be made from that run's phase rows,
using the same exact equation and quality gates. If a currently uncached phase
shows repeatable negative net economics, promote it to 5m. If a cached phase is
non-negative on a meaningful sample, turn it off. One-hour caching should
remain opt-in until a real phase demonstrates the multiple reads needed to
repay its larger write premium.
