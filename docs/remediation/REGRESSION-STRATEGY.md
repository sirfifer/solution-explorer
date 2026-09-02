# Regression strategy: proving a build produces the results we want

Matured 2026-07-20 from owner direction. Companion to ROBUSTNESS-STRATEGY.md.
That document is about building safely (nothing ships a fracture or breaks the
run). This document is about the complementary question: after we change the
engine, does the new build actually produce the results we want, and can we see
what changed versus the last build so nothing slips through the cracks.

## The named pattern

This is golden-master testing, also called approval or characterization testing,
applied at the whole-projection level. You freeze a known input, generate the
full output, and treat that output as the approved baseline. On the next change
you regenerate and diff against the baseline. Any difference is a signal: an
intended improvement, or a regression to investigate. It is the system-level
analog of the per-commit byte-parity tests, run on real data at scale rather
than on fixtures.

## Blue/green (two slots), for demo and dogfood

Always keep the previous full projection alongside the new one, for both the
demo and the dogfood, so a build can always be compared to the one before it.
Cloudflare Pages gives part of this free: every deploy is a versioned URL and
the alias is the live "green" slot, so the prior deployment URL is the "blue"
slot for comparison. The new capability we need is a projection-diff tool.

## The projection-diff tool (candidate build)

A deterministic diff over two full projections that reports what changed in
terms a human and CI both read: component count and identity deltas,
relationship deltas by kind, finding deltas by kind (new, resolved, changed
rank), coverage and inventory deltas, entity and capability deltas, and
enrichment coverage deltas. The output answers "did this change improve or
regress the representation of this project," which is the judgment the owner
wants to make continuously, especially for the demo.

## Three targets

1. DEMO: the owner's iOS app (unamentis-ios). Public, must show well, and it
   changes over time (real project under development). A diff here mixes our
   engine changes with the project's own changes, so it is a health check, not a
   clean regression signal.
2. DOGFOOD: the self-repo (solution-explorer). Local, always dogfooded, also
   changes over time. Same mixed-signal caveat.
3. GOLDEN CORPUS (new): a static local clone of a respected, popular, real-world
   repository, held FROZEN (not kept in sync with its remote) precisely so that
   any new-generation-versus-old-generation diff is attributable to OUR engine
   change, not to the target moving. This is the clean regression signal the
   other two cannot give. Periodically, at a stopping point, update the clone and
   re-baseline so we never fall far behind the real project's current state.

### Golden corpus candidate (validated 2026-07-20)

An independent fresh validation reshaped this into a TWO-CORPUS pairing, which
is better than either repo alone. The two corpora play different roles.

- FLASK (pallets/flask, BSD-3-Clause, ~8-10k core LOC, 3.1.3). Build the harness
  on this FIRST. For the regression role specifically, stability and low diff
  noise matter more than demo dazzle, and Flask is the more stable, smaller,
  permissively-licensed choice. It is also a SWE-bench standard repo, which gives
  external comparability ("our corpus is also SWE-bench repo Flask") that
  resonates with a technical audience. It exercises routing, blueprints, the
  app-factory, and context locals; it is thinner on dependency injection and
  data-entity lenses.
- FASTAPI (tiangolo/fastapi, MIT), PINNED at 0.139.2 or later and with the
  translated docs excluded from the scan. Add this SECOND for lens breadth and
  demo value: it is the richest single-repo surface for this tool (routing,
  Depends DI, Pydantic data entities, OpenAPI capabilities) and maximally
  recognizable. Caveat that drove the pin: FastAPI 0.137.0 (June 2026) shipped a
  major router-internals refactor that changed the router.routes shape and broke
  tools walking it; pinning post-refactor baselines the settled tree, and
  freezing a commit neutralizes the ongoing docs/translation churn. Single
  maintainer and no benchmark comparability are the other honest tradeoffs.

Rationale for the order: the golden corpus's primary job is a clean regression
signal, so the FIRST target should maximize stability and minimize noise while
the harness itself is being shaken out (Flask). The SECOND adds lens breadth and
demo strength once the harness is proven (FastAPI). The research's alternative
(FastAPI first for breadth) is defensible; the owner decides the order, but the
pairing and the FastAPI pin are the firm recommendations.

Keep large-repository-validation as a SEPARATE scale proof (3.47M lines is a scale benchmark, not a
daily-diff corpus). Django is deliberately excluded here (the richest benchmark
repo but 500k+ LOC, too large for a frequent full diff). Add a respected
TypeScript repo later for language diversity (NestJS is the strongest fit on the
merits: decorator DI, modules, controllers), and a Swift option (Alamofire) if
the Swift path wants a golden target. Eventually a multi-repo "golden solution"
once M1 multi-repo matures.

## Cadence

- On every major engine change: full regeneration of the demo and the dogfood,
  deployed to the green slot with the prior build retained in blue, and a
  projection diff reviewed. This is already partly practiced (we regenerate and
  redeploy after each significant merge); the addition is retaining the prior
  build and running the diff.
- Golden-corpus diff: on demand and, ideally, in CI on a change to the engine,
  against the frozen baseline. A non-empty diff that is not an intended
  improvement is a regression to investigate before merge.
- Re-baseline the golden corpus at stopping points (update the clone, regenerate,
  approve the new baseline) so it tracks the real project without ever being the
  source of noise between engine changes.

## The parity cross-check

The golden corpus doubles as the real-data proof of the incremental-equals-full
parity contract from ROBUSTNESS-STRATEGY.md. On the frozen clone, a full cold
regeneration and a warm incremental run must produce the same projection. A diff
between them at scale, on real code, is the strongest evidence that the
light-handed auto-update path is trustworthy and that a daily full regeneration
would add nothing. This is how we validate the contract without having to
rehearse everything in production.

## Candidate cards (design here, owner green-lights builds)

- G1: the projection-diff tool (deterministic, human- and CI-readable deltas
  across all projection sections).
- G2: the golden-corpus harness (a frozen local clone, an approved baseline, a
  re-baseline procedure, CI wiring), with FastAPI as the initial target.
- G3: the two-slot retention practice for demo and dogfood deploys (keep blue,
  promote green, diff), a small addition to the existing redeploy flow.
- G4: the golden-corpus full-vs-incremental parity check at scale (uses G1 and
  G2).
