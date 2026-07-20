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

### Golden corpus candidate

Recommended primary: FastAPI (tiangolo/fastapi). It is widely respected and
recognizable (shows well), a clean and real-world single-repo Python codebase of
moderate size (good for a daily diff, not so large it is unwieldy), and it
exercises the tool's Python strengths plus a rich structure (routing,
dependency injection, capabilities and entities) that lights up multiple lenses.
Keep vscode as a SEPARATE scale proof (3.47M lines is a scale benchmark, not a
daily-diff corpus). Consider adding a respected TypeScript repo later for
language diversity, and eventually a multi-repo "golden solution" once M1
multi-repo matures. The specific pick is the owner's call; FastAPI is the
default recommendation.

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
