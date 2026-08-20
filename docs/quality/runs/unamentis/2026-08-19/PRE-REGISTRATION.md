# Pre-registered expectations, N1 calibration run

Written 2026-08-19 **before any sitting had produced a findings document**, and
before the retrospective baseline was scored. Recorded so that these cannot be
retrofitted once the results are in. Each is falsifiable.

Verified at time of writing: the P1 sitting was in progress and had produced
screenshots but no `FINDINGS.md`; P2 and P3 had not started; the baseline
scoring job had not reported.

## Why pre-register at all

The orchestrator both builds the answer key and judges the results. That is
unavoidable here, since the charter disqualifies the orchestrator from sitting
and requires it to verify. The compensating control is to state in advance what
we expect to find, so that a comfortable interpretation after the fact is
visible as one.

## E1. External dependencies will be under-answered, and it will be the map's fault

The published dataset exposes **five** named third-party services: Anthropic,
Deepgram, GitHub, Groq, OpenAI. Independent reading of the subject's own source
found materially more: Google as an LLM provider, AssemblyAI for speech to text,
ElevenLabs and Deepgram Aura for text to speech, Ollama as the self-hosted
model runtime, Unleash for feature flags, and LiveKit as an optional real-time
transport.

The supply-chain and SBOM section is marked `present: false` in the published
`ai.json`, and no `sbom.json` shard exists.

**Prediction.** P1 question 4 and P2 question 3, both of which ask what the
system depends on externally, will score `partial` at best, and the cause will
be that the information is absent from the projection rather than that the
reviewer failed to find it.

**How to tell the difference.** If a persona names providers beyond the five,
this prediction is wrong and the map carries more than the manifest suggests. If
a persona names exactly the five, or fewer, check whether the map offers any
route to the rest before scoring the persona down.

**Falsified if:** any persona names a provider outside those five from the site
alone.

## E2. The coverage ledger is absent, not merely incomplete

The charter's profile asks whether the coverage ledger is complete. It does not
exist: no top-level `coverage` key in the manifest, `present: false` in
`ai.json`, and `/architecture/coverage.json` resolves to the SPA shell on the
live origin rather than to a document.

**Prediction.** If any persona is told by the interface that coverage
information exists, that is a blocked path at the severity they hit it. P3 is
most likely to find this, because P3 is briefed to chase advertised URLs.

**Falsified if:** a coverage ledger turns out to be reachable by some route.

## E3. The single-laptop fact is the highest-value thing in the subject, and may not be reachable

The subject's own infrastructure document names its production host as one
laptop and lists, verbatim, "Single point of failure" among that host's
disadvantages. Every backend service is co-located there.

**Prediction, deliberately two-sided.** Either P2 reaches it, in which case this
is the strongest commercial evidence the run can produce, or P2 cannot, in which
case the tool cannot answer the single most important question an executive
would ask of an architecture map.

**This is recorded as a finding either way**, and is checked during verification
regardless of what P2 says.

## E4. Enrichment coverage disagrees with a prior gate record

Measured today: 250 of 254 components carry enrichment, 98.43%. `DEPLOYMENTS.md`
records "251/251 enhanced components preserved" for the same install.

**Prediction.** These are counting different populations rather than evidencing
a regression. Not investigated yet, and deliberately not investigated before the
sittings, so the number is not disturbed mid-run.

**Falsified if:** reconciliation shows enrichment was actually lost.

## E5. The baseline will be a floor, not a score

P3's findings document from 2026-08-17 does not exist, so several of its
dimensions cannot be supported and will be null. The scorer reports any run with
unscored dimensions as a floor.

**Consequence to state plainly in the report.** Any improvement measured against
P3's baseline is a lower bound on the improvement, not a measurement of it.

## What would make this run untrustworthy

Recorded now, so it is not negotiated later:

- A persona showing knowledge it could not have got from the site. The sitting
  is discarded, not adjusted.
- A key entry found to be wrong during verification. The question becomes
  unscoreable retrospectively and the change is recorded in the retro.
- The mirror diverging from the live origin during the run. Re-verify before
  publishing any number.
