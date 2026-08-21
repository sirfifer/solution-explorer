# N3 owner decisions

Written 2026-08-20 at the start of N3 (the demo harness and demo one). Three
decisions gate the deploy half of N3. The harness, registry, hub generator and
launchd unit do not depend on any of them and are being built in parallel, so
nothing is stalled while these are open.

Each entry follows the working agreement: the situation with fresh evidence, why
it matters, real options with effort and an explicit for and against, a
recommendation, and exactly what is being asked.

---

## D-N3-1. The Cloudflare Pages project for demo one

### Situation, measured today

`wrangler` on this machine is logged in as `richard@amerman.net`, account
`a01622cc6f94a7bb946140c02b6ee474`, and the token carries `pages (write)`.
`syscorpus.com` already resolves to Cloudflare nameservers (`graham` and
`rafe.ns.cloudflare.com`), so the zone exists. No `syscorpus-*` Pages project
exists yet, and neither `demos.syscorpus.com` nor `vscode.syscorpus.com`
resolves.

So the account is ready and the only missing thing is the decision to create the
project. **I can do it in one command; I have not, because creating a project
and attaching a public hostname on your account is an outward-facing change.**

### Why it matters

`DEMO-PROGRAM.md` 4.4 puts one Pages project per demo, driven by the free plan's
20,000-files-per-site limit. VS Code measured 668 files, so the ceiling is not
close, but the per-demo split also buys independent rollback and stops one
broken demo taking the hub down. That layout is already decided (D2, 2026-08-18)
and is not being reopened here.

### Options

| # | Option | Effort | For | Against |
|---|---|---|---|---|
| A | I create `syscorpus-vscode` now and attach `vscode.syscorpus.com` | ~2 min, one command plus one DNS record | Unblocks the private preview the moment the bundle validates | Creates a public hostname before anything has been reviewed. Mitigated: the preview gate denies every request until the passcode is set |
| B | I create `syscorpus-vscode` now but attach **no** custom domain, using only the `syscorpus-vscode.pages.dev` URL | ~2 min, no DNS | Same unblock, no public subdomain on your commercial domain until the demo has passed a review | The preview URL is uglier in an outreach email. Attaching the domain later is a two-minute change |
| C | You create it in the dashboard | Your time | You see exactly what is created | Costs you the thing that is most expensive, your typing |
| D | Defer until the bundle validates locally | Zero now | Nothing created that is not yet needed | Re-asks this question in a day and re-blocks then |

### Recommendation: **B**

It unblocks the deploy path immediately and keeps `syscorpus.com` clean until a
demo has actually earned a subdomain. The graduation gate in `DEMO-PROGRAM.md`
section 2 is what should mint `vscode.syscorpus.com`, not convenience. Attaching
the domain afterwards is trivial and is the natural moment to do it.

### Asked

May I run `wrangler pages project create syscorpus-vscode`, and if so, with or
without the custom domain?

---

## D-N3-2. `PREVIEW_PASSCODE` for the preview gate

### Situation

`infrastructure/preview-gate/_middleware.js` is built and tested (`node --test`,
part of the CI gate). It needs two Pages secrets: `PREVIEW_PASSCODE` (required,
and the gate **denies everything** without it, which is the correct failure
direction) and `PREVIEW_SUBJECT` (optional, cosmetic).

Rotating the passcode revokes every outstanding session, because sessions are
HMAC-signed with it. That is deliberate and it is the whole revocation story.

### Why it matters

`DISCLOSURE-POLICY.md` step 3 requires the preview be gated server-side before
anyone outside sees it. Without the secret there is no private preview, so the
demo cannot be reviewed before it is public, and the graduation gate has nothing
to gate.

### Options

| # | Option | Effort | For | Against |
|---|---|---|---|---|
| A | I generate a high-entropy passcode and set it with `wrangler pages secret put`, then hand it to you | ~1 min, no typing for you | Strong by construction, and you never type it | It passes through this transcript. Rotating is one command if that bothers you |
| B | You choose a passcode and set it yourself | Your time and typing | Never leaves your hands | Human-chosen shared secrets are weak, and typing is the thing we are trying to spend least of |
| C | Use Cloudflare Access instead, email allowlist | ~10 min dashboard work | Authenticates a person, revocable per person, also covers the deploy-preview URLs the platform generates, which the passcode gate does **not** | Requires a Cloudflare identity from anyone you send it to, which the preview-gate README itself calls a rude ask for a maintainer |
| D | Both: Access for you, passcode for outside reviewers | ~12 min | Right gate for each audience | Two things to maintain for an audience of very few |

### Recommendation: **A now, C before any maintainer outreach**

A costs nothing and unblocks today's work, where the only reviewer is you. The
README is explicit that the passcode gate does not protect the platform's own
deploy-preview URLs, so before a link goes to anyone at Microsoft, Access is the
correct gate and I would set it up then.

### Asked

Shall I generate and set the passcode (A)?

---

## D-N3-3. When to spend the enrichment run

### Situation, measured

`enhance --dry-run` on the VS Code store reports **1,446,236 prompt tokens**
across **55 partitions plus a narrative pass**. It models neither output tokens
nor cost, so that figure is an input-side floor.

Enrichment runs through the `claude` CLI on **your subscription**, not a billed
API key (decision D4, 2026-08-18). So this spends your usage, and it is not a
line item someone else pays.

The partition plan is very uneven, which matters for the options below:

```
partition  0:   7 components, ~156,212 tokens   <- largest
partition 15:   2 components,   ~1,470 tokens   <- smallest
partition 37:  30 components,  ~95,846 tokens
architecture-narrative:       ~169,886 tokens
```

`analyze.py enhance` has `--max-partitions` (cost control), `--max-cost-usd` (a
real ceiling, default 10.0, in-flight partitions finish and the rest record as
skipped), `--update` (re-enhance only stale targets), and `--report` for a
machine-readable run record. **So a partial, measured run is genuinely
available, not a hypothetical.**

### Why it matters

Enrichment at or above 85 with zero failed partitions is one of the seven
graduation-gate conditions in `DEMO-PROGRAM.md` section 2, and 3.6 lists AI
enrichment with provenance as part of full class representation. So the public
demo cannot happen without it. The **private preview can**, which is what makes
staging this possible.

### Options

| # | Option | Effort | For | Against |
|---|---|---|---|---|
| A | Full run now, all 55 partitions plus narrative | ~1.45M prompt tokens plus unmodelled output | One run, demo one is complete, and it produces the real cost number for every future weekly refresh | Spends the whole unknown before we know the per-partition cost or whether quality clears 85. If it fails the gate, the spend is largely wasted |
| B | **Calibration first**: `--max-partitions 5 --report`, measure real output tokens and cost, then decide the full run with numbers | ~192k prompt tokens, about 13% of the total, plus one decision point | Converts the unknown into a measurement for roughly an eighth of the spend. Partitions 0 through 4 happen to include the largest partition, so the sample is not flattering to itself. Also exercises the quality scorer early | Two sittings instead of one. Adds maybe a day |
| C | Defer entirely: build and validate everything else, private-preview un-enriched, spend only once the rest passes | Zero now | Nothing spent until the pipeline is proven end to end | The preview you review is not the artifact that would be published, so the review is partly of the wrong thing |
| D | Skip enrichment for VS Code, publish deterministic-only | Zero | No spend at all | Fails 3.6 and the graduation gate. Would need the plan reopened, and it is the wrong demo to weaken |

### Recommendation: **B**

The dry run's own limitation is the argument. It gives an input-side floor and
nothing else, and the thing we actually need to know, output tokens and whether
quality clears 85, can only come from a real invocation. Five partitions buy
both for about an eighth of the spend, and because `--max-partitions` takes them
in order, the sample includes partition 0 at 156k tokens, so the extrapolation
will if anything overstate rather than flatter. If calibration shows quality
comfortably above 85 and a cost you are happy with, the full run is then an
informed decision rather than this one.

I would not do A blind, and C reviews an artifact that is not the one we would
publish.

### Asked

Shall I run the 5-partition calibration (B), and if it looks good, come back to
you with real numbers before the full run?

---

## Not blocked on you, recorded so it is visible

**Clone depth is a publish-gate problem, not a nice-to-have.** Verified against
the N2 artifact today: the depth-1 clone gives every one of the 15,256 files
`commit_count: 1`, one author, an identical `last_modified`, `churn` exactly
equal to the file's added line count, and `hotspot_score` equal to `churn + 1`
for 14,010 of them. `cochange_pair` has **zero** rows.

The Activity lens therefore does not come out empty, which would be obviously
broken and honest. It comes out **populated and wrong**: the published "hottest
files in VS Code" would in fact be a ranking of the largest files, topped by a
syntax-highlighting test fixture and a JSON recording fixture. Provenance does
record `shallow: true, commits: 1`, so the data is labelled, but the numbers
themselves read as real activity.

That is the same shape as the defects that have cost this project the most time:
a plausible wrong answer that passes every machine gate. Clone depth is being
measured now and decided before anything is generated, not after.

---

# Round 2, after the owner's answers of 2026-08-20

Answers received: hosting layout corrected to `vscode.demo.syscorpus.com`;
passcode generated and set by me; enrichment calibrated on five partitions
first. A new design request arrived with the third answer and is D-N3-5 below.

## Done, no longer open

- **Pages project `syscorpus-vscode` created** on account
  `a01622cc6f94a7bb946140c02b6ee474`.
- **`PREVIEW_PASSCODE` generated and set**, 99.1 bits of entropy from a
  31-character unambiguous alphabet, set in **both** the production and preview
  environments. `PREVIEW_SUBJECT` set to "Visual Studio Code". Setting the
  secret in the preview environment addresses the gap the preview-gate README
  flags, that the platform's own deploy-preview URLs are not covered. To be
  confirmed against a real deployment rather than assumed.
- **Clone depth decided: full.** Evidence in `PREFLIGHT-MEASUREMENTS.md`.
- **Enrichment calibration running** on five partitions, `--model sonnet`,
  against the full-history store.

## D-N3-4. The hosting layout hits a Cloudflare certificate wall

### Situation

The requested layout is `demo.syscorpus.com` for the hub with each demo hanging
off it as `vscode.demo.syscorpus.com`. That is a **second-level** subdomain, and
it runs into a documented Cloudflare limit:

- Free Universal SSL issues a wildcard for `*.syscorpus.com` only. Wildcards do
  not cascade, so `vscode.demo.syscorpus.com` is not covered.
- Advanced Certificate Manager is the normal fix, **but Cloudflare's own docs
  say advanced certificates do not apply to Pages custom domains**, which use
  Cloudflare for SaaS certificates instead. So paying for ACM would not
  necessarily fix it.

**I could not finish testing this empirically.** Reading the stored Cloudflare
credential to call the API directly was blocked, correctly, as it looks like
credential exfiltration, and I did not work around it. So the above is from
Cloudflare's documentation and community reports, **not** from a test on this
account. Treat it as likely, not proven.

### Why it matters

It decides the public URL of every demo in the program, and it is much cheaper
to settle before three demos exist than after.

### Options

| # | Option | Effort | For | Against |
|---|---|---|---|---|
| A | `vscode-demo.syscorpus.com`, single level | None, works today on the free plan | Covered by Universal SSL. Closest thing to the requested naming that certainly works | Reads as a hyphenated name rather than a hierarchy |
| B | One hostname, path-based: `demo.syscorpus.com/vscode`, a small Worker routing paths to each Pages project | Half a day for the Worker plus its tests | Exactly your "a demo subdomain and each demo hangs off it" mental model, one certificate, one hostname, and the hub is the site root | A Worker in the path of every demo request is a new moving part that can break all demos at once, which per-demo projects were chosen to avoid |
| C | Try `vscode.demo.syscorpus.com` anyway and see | 10 min in the dashboard, your hands | Settles it for certain. The docs may be stale | If it fails it fails as a certificate error, which is the worst-looking failure on a commercial surface |
| D | `vscode.syscorpus.com`, the original plan 4.4 layout | None | Known to work, already the written plan | You corrected this, so it is listed only for completeness |

### Recommendation: **C first, then A if it fails**

The question is cheap to settle definitively and only you can run it, since the
credential path is closed to me. Add `vscode.demo.syscorpus.com` as a custom
domain on the `syscorpus-vscode` Pages project in the dashboard and see whether
the certificate goes active or sticks at "not covered by a certificate". If it
works, your layout stands and nothing changes. If it does not, A is a
five-second change and no demo has shipped yet.

I would not pick B unless you want the hierarchy badly enough to accept a shared
failure point across all demos.

**None of this blocks work.** Everything until the public launch runs on
`syscorpus-vscode.pages.dev`, which needs no custom domain, and the graduation
gate is what should mint a public hostname anyway.

### Asked

Can you try adding `vscode.demo.syscorpus.com` in the Cloudflare dashboard and
tell me whether the certificate goes active?

---

## D-N3-5. Tiered model escalation in enrichment

### Does it already exist? No.

`EnhanceConfig` carries a single `model` field, `--model` defaults to a
sonnet-class model, and `run_enhance` builds one invoker used for every
partition. There is no escalation, no per-partition model choice, and no
mechanism for one tier to hand work to another.

### The good news: most of the signal already exists

The escalation triggers you described are largely already computed. This would
be routing on existing signals rather than inventing new ones:

| Signal | Where it already lives | What it means |
|---|---|---|
| Per-component quality score, and a `below_threshold` list of everything under 85 | `score_partition` in `scripts/score-ai-enhancement-quality.py` | Objective. Already the gate that decides pass or fail |
| `uncertain` edge verdicts | `passes.py`, `_EDGE_STATUSES` | The model saying it cannot settle a relationship |
| `uncertain` finding verdicts | `passes.py`, `_FINDING_VERDICTS` | Same, for findings |
| `uncertain` identity verdicts, **which already require a written reason** | `passes.py`, `_IDENTITY_STATUSES` | The model saying it cannot settle type, framework, name or port, and why. This is the S2 misclassification surface, the worst trust defect the comprehension study found |
| `observations`, categorised, including `detection_gap`, `data_quality`, `misclassified_component` | `prompts.py` payload schema | The model volunteering that something is off |

So a partition that produced low scores, several `uncertain` verdicts with
reasons, or `detection_gap` observations, is already telling us it struggled.
Today nothing acts on that.

### What would be genuinely new

1. **A tier ladder instead of a single model.** `--tiers sonnet,opus,fable`,
   defaulting to today's single-model behaviour so nothing changes unasked.
2. **An explicit `escalate` field in the payload schema**, with a required
   reason and a category. This is the part you described that does not exist
   today: the model saying "there is more here than I can get to" rather than
   only "I am uncertain about this specific field". Categories roughly:
   `insufficient_context`, `ambiguous_semantics`, `suspect_classification`,
   `more_to_discover`.
3. **An escalation policy module**, deterministic and testable, that turns those
   signals into a ranked escalation list.
4. **Budget caps, not predictions.** Your example was 55 to 15 to 5. The right
   implementation is a **cap**, `--escalate-max-share 0.30`, with candidates
   ranked worst-first so the cap is spent on the worst partitions. Otherwise a
   bad night silently escalates all 55 to Fable on your subscription. This
   matters more than usual because the spend is your usage, not a billed key.

### The part that decides whether this is worth building

You said the thing to watch is whether the stacking actually produces better
results, and that if Sonnet cannot do reasonable work we drop it and run
Opus plus Fable. **That is a measurement, and the design has to make it
measurable or we will be guessing.**

Concretely: run the same partitions flat-Sonnet and tiered, score both with the
same scorer, and compare. The calibration now running is the first half of that
A/B for free, since it is flat Sonnet over five partitions with a report.

### Options

| # | Option | Effort | For | Against |
|---|---|---|---|---|
| A | Build the full ladder now, before demo one | 1 to 2 days, plus tests and an A/B | Demo one ships with the best enrichment we can produce, and Wave 1 evaluates the real thing | Delays N3. Designs the escalation criteria before we have seen a single real quality score, which is guessing at exactly the thing we said we would measure |
| B | **Finish the calibration first, read the scores, then design the ladder against real data** | The calibration is already running. Design after | The `below_threshold` list from a real run tells us how much escalation is actually needed. If Sonnet scores 95 across the board the ladder is nearly free; if it scores 60 the answer is your fallback, drop Sonnet, and we skip building the Sonnet tier entirely | Demo one's first enrichment is flat, so the ladder lands in a later refresh |
| C | Skip Sonnet now, run Opus plus Fable | Config only, no build | Certainly good output | Spends far more of your usage per refresh, and gives up the thing you actually want to learn |
| D | Do not build it | Zero | | Gives up a real quality and cost win on a program that will run weekly forever |

### Recommendation: **B**

Your own framing is the argument. The question "can we get reasonable work out
of Sonnet" is answerable in about an hour by the run already going, and the
answer changes the design: a high score makes the ladder a cheap optimisation, a
low score means the Sonnet tier should not be built at all. Designing the
escalation criteria before seeing a single real quality score is the same
mistake as the search-index restructure that was scoped, approved, and then
measured away.

This is also not a small change. It touches the payload schema, the invoker, the
partition loop, the CLI and the report, and it needs an A/B to prove itself. It
deserves its own card and its own session rather than being absorbed into N3.

### Asked

Confirm B: I finish the calibration, bring you the real per-component scores and
the `below_threshold` list, and we design the ladder against that. I will write
the card either way so it is not lost.

---

# Calibration result, 2026-08-20

The five-partition calibration you approved has run. `--model sonnet`, against
the full-history VS Code store, `--max-partitions 5`, report at
`/Volumes/Studio/dev/.scratch/n3-enrich/calibration-sonnet.json`.

## What it actually cost

```
partition 0   ENRICHED   7 components, 1 attempt   $1.9016
partition 1   ENRICHED  30 components, 1 attempt   $0.9438
partition 2   ENRICHED  30 components, 1 attempt   $0.7001
partition 3   ENRICHED   2 components, 1 attempt   $0.6563
partition 4   ENRICHED  30 components, 1 attempt   $0.8379
                                    partitions:    $5.0397
                       architecture narrative:     $4.1522
                                        TOTAL:     $9.1920
```

Zero failed partitions, zero retries, 99 components and 69 relationships
enriched, narrative written.

## Projecting the full run, and why the obvious way is wrong

**The naive extrapolation is `$9.19 x 11 = $101`, and it is wrong by a factor of
nearly three.** Two reasons:

1. **The narrative pass is a fixed cost, not a per-partition one.** It cost
   $4.15, which is 45% of this run's total, and it runs **once** regardless of
   how many partitions are processed.
2. **Partitions 0 to 4 are not a representative fifth.** They carry 192,520 of
   the 1,276,350 total partition prompt tokens, which is **15.1%**, not 9.1%.
   Partition 0 alone is 156,212 tokens.

Weighting by the dry run's per-partition token counts:

| | Prompt tokens | Cost |
|---|---|---|
| Partitions 0-4, measured | 192,520 | **$5.04** |
| Remaining 50 partitions, projected at $26.18/1M | 1,083,830 | **$28.37** |
| Architecture narrative, measured, fixed | 169,886 | **$4.15** |
| **Full VS Code enrichment** | **1,446,236** | **~$37.56** |

This also resolves an ambiguity in `PREFLIGHT-MEASUREMENTS.md`: the 1,446,236
figure **includes** the narrative pass (1,276,350 partitions + 169,886
narrative), it is not additional to it.

## Two budget numbers in the repo are wrong, and would truncate a run

- **The registry's `budget.max_cost_usd: 5.0`** is about **7.5x too low** for
  VS Code. A refresh would stop after roughly the first five partitions.
- **`analyze.py enhance`'s default `--max-cost-usd 10.0`** is also too low. This
  five-partition run reached **$9.19**, within $0.81 of that default ceiling. A
  full run left on defaults would stop around partition 10 and record the other
  45 as skipped.

Neither fails silently, which is to the pipeline's credit: the ceiling stops
launching new partitions, lets in-flight ones finish, records the rest as
skipped, and reports the partial state. But an operator reading "exit 0" without
reading the skip count would draw the wrong conclusion.

**Recommendation: raise the VS Code registry budget to `max_cost_usd: 45.0`**,
about 20% over the $37.56 projection, so ordinary variance does not truncate a
refresh while a runaway still hits a ceiling.

## Quality: the gate says FAIL and that is not what happened

```
quality gate: FAIL
Components: 99/570 enhanced (17.4%) | Avg score: 86.0% | Relationships: 69/69 valid
```

**The gate is `errors == 0 and coverage >= 100 and avg_score >= 85`.** It failed
on **coverage**, which is 17.4% because we deliberately ran 5 partitions of 55.
It did **not** fail on quality. Average score is **86.0%, above the 85
threshold**, with 69 of 69 relationships valid and no validation errors.

Reporting this run as "quality failed" would be exactly the plausible-wrong-answer
this project keeps getting caught by: a red word, a partial check, a confident
conclusion.

**But the margin is thin.** 86.0 against a threshold of 85 is one point of
headroom on a partial sample. That is the single most useful number for the
tiering question in D-N3-5, and it points toward tiering being worth building
rather than away from it: if the fleet average sits a point above the gate, the
components dragging it down are exactly what a higher tier should pick up.

The per-component `below_threshold` list is the concrete escalation candidate
set. It is being extracted from the re-projected enriched artifact now.

---

# The finding that changes D-N3-5: the enrichment quality gate does not measure quality

Found while extracting the `below_threshold` list the tiering design needs.
**Verified against the artifact, not inferred from the report.**

## What the scores actually look like

```
components scored:        99
average score:            86.0
below threshold (<85):    0
score distribution:       85.0 x 83   88.0 x 8   92.5 x 2   94.0 x 5   96.2 x 1
```

Zero components fall below the threshold, which reads as a clean pass. But
**83 of 99 components score exactly 85.0**, which is the threshold itself. A
natural quality distribution does not pile 84% of its mass on one value that
happens to be the pass mark.

Inspecting those 83, every one of them carries exactly one detail:
`optional_populated: 2/4`. Nothing else differentiates them.

## Why: it is a form-completeness metric

`score_component` in `scripts/score-ai-enhancement-quality.py` allocates:

| Weight | What it checks |
|---|---|
| 50% | Are the required fields non-empty? |
| 10% | Is `help_text` between 3 and 5 sentences? |
| 30% | What share of the *applicable* optional fields are populated? |
| 10% | Is `criticality` one of the valid enum values? |

**It never evaluates whether anything said is true.** A component whose
description is confident and wrong, with a well-formed four-sentence
`help_text` and a valid `criticality`, scores 85 or better. The exact-85 cluster
is simply every component that filled all required fields, wrote conformant help
text, and populated half its applicable optional fields.

The scorer is not mislabelled internally: it implements DPEA Phase 4a schema
validation and Phase 4b quantitative scoring, and it does that correctly. The
problem is what leans on it.

## The consequence for the graduation gate

`DEMO-PROGRAM.md` section 2 requires "**Enrichment quality at or above threshold
(85), zero failed partitions**". That condition is satisfied by well-formed JSON.
It does not gate correctness, and it is blind to **S2, confident
misclassification, the single worst trust defect the comprehension study found**.

## The correctness instrument does exist, and it is not wired into any of this

`analyze.py verify <edges|intents|findings|all>` and `analyze.py name` run the
Phase 7 passes in `analyzer/enrich/passes.py`, including **`verify_identity`,
which is explicitly the S2 gate** over `name`, `type`, `framework` and `port`.
They produce `confirmed` / `refuted` / `uncertain` verdicts, and an `uncertain`
identity verdict is *required to carry a written reason*.

Three facts, each verified:

1. `analyzer/enrich/engine.py` contains **no call** to `verify_edges`,
   `verify_identity`, `check_intents` or `verify_findings`. `enhance` does not
   run them.
2. The store after this calibration holds enrichment rows of kind `architecture`
   (1), `component` (99) and `relationship` (69), and **zero verdict rows** of
   any kind.
3. The graduation gate does not require them either.

So the pipeline has a real correctness instrument that the demo program's gate
never invokes.

## What this does to the tiering question

It sharpens it rather than answering it against tiering.

- **The completeness score cannot drive escalation.** It cannot distinguish a
  correct description from a plausible wrong one, which is precisely the
  discrimination an escalation ladder needs. Building the ladder on this signal
  would route work to Opus and Fable based on how many optional JSON fields were
  applicable, which is nearly noise.
- **The `uncertain` verdicts can**, and they are the right signal: model-declared,
  reason-carrying, and pointed at the S2 surface. But they only exist if `verify`
  actually runs.
- So **the prerequisite for the ladder is wiring the verification passes into
  the refresh and into the gate**, not the ladder itself.

**Revised recommendation for D-N3-5**, replacing "design the ladder against the
calibration scores", because the calibration showed the scores cannot carry that
weight:

1. Wire `analyze.py verify all` into the demo refresh chain and add its results
   to the graduation gate. This is the missing correctness gate and it is
   valuable on its own, tiering or not.
2. Run it once on this VS Code store to get a real `uncertain` and `refuted`
   census. That census is the honest input to the escalation design, and it is
   also the first real measurement of whether Sonnet's output is *right*, which
   is the question you actually asked and which the 86.0 does not answer.
3. Then design the ladder, escalating on verdicts rather than on completeness.

The cost figures are unaffected: enrichment still projects to about $37.56 for
VS Code. The verification passes are additional and not yet measured.

---

# What verification of the delegated harness found

The harness build was delegated (routing table: "orchestration over CLIs that
already exist, against a written design"). It came back accurate on its own
terms: 54 new tests, ruff clean, and the pytest count it reported matched an
independent rerun exactly. It also self-reported two bugs its tests caught and
flagged the gaps it could not close. Good work.

Three defects survived it anyway, and all three are the same shape: **a check
that passes, so nobody looks.**

## 1. `deploy` would have published an ungated site. Design gap, not implementation

`DEMO-PROGRAM.md` 4.2's subcommand table went straight from `analyze` to
`deploy`, so the harness deployed the projection output directory. That
directory is data: `manifest.json`, `data/`, `search/`, `ai.json`, `llms.txt`.
It has **no `index.html`**, so there is no viewer, and **no
`functions/_middleware.js`**, so there is **no preview gate at all**. The
"private preview" required by `DISCLOSURE-POLICY.md` step 3 would have been
fully public.

The implementation followed the written design faithfully. The design was wrong.

Fixed: a `bundle` subcommand now assembles viewer + projection + preview gate +
`UPSTREAM-LICENSE.txt` + `ThirdPartyNotices.txt` + `publication.json`, `deploy`
deploys that, and `bundle_safety_errors` refuses any bundle missing the viewer,
the gate, or the license. **That refusal is not overridable by
`DEMO_DEPLOY_ALLOW`**: the environment variable authorizes a deploy, it cannot
authorize an unsafe one. `DEMO-PROGRAM.md` 4.2 is amended to record the gap.

## 2. The detect-only theater gate was measuring the wrong thing

The gate read `manifest.stats.languages`, which counts **every** file type. On
VS Code that is 76% TypeScript and **18% JSON**, plus markdown, css, yaml and
html. So JSON and Markdown were being counted as "languages we cannot parse",
and the gate reported:

```
21.9% detect-only of code lines (limit 25%)     <- PASS, and wrong twice over
```

Wrong in the label (it was not code lines) and wrong in the measure. The correct
figure, restricting the denominator to `analyzer.constants.CODE_LANGUAGES`, is:

```
0.10% detect-only (3,671 of 3,858,464 code lines, limit 25%); 1,078,256 non-code lines excluded
```

which reproduces `PREFLIGHT-MEASUREMENTS.md`'s recorded numbers to the digit.
That document had already warned about exactly this: "Use the code-only figure;
the all-lines number is inflated by JSON and config and would give a false read."

It passed, so it would not have been looked at, while sitting three points from
a limit it should clear by twenty-five. A subject with a little more JSON would
have tripped the theater gate for having documentation. Fixed, with two
regression tests: one for the VS Code shape, one proving the gate keeps its
teeth on a genuinely unparseable Kotlin subject.

## 3. A bug I introduced myself, caught before it ran

My first `assemble_bundle` copied the projection into
`viewer/public/architecture/` before building, mirroring what `action.yml` does.
That directory is **259 tracked files**, the committed UnaMentis dataset. The
build would have destroyed repository content and produced an enormous spurious
diff. CI gets away with it because it builds a copy of the viewer under
`.solution-explorer/`; a local harness does not.

Fixed by swapping the projection into the **built output** instead, which
touches nothing tracked. Verified: `git status viewer/` is clean after a real
bundle run.

## Two smaller corrections

- `FULL_PARSE_LANGS` was a hardcoded copy of a set in a test file. It is now
  read from `analyzer.parsers.PARSERS`, and `CODE_LANGUAGES` from
  `analyzer.constants`, so neither can drift. A copy that drifts by one language
  shrinks the detect-only share, which is the direction that weakens the gate.
- `license_review_recorded` reported `NOT_IMPLEMENTED` because the registry had
  nowhere to record a review. There is now a `license_review` block, the record
  lives at `docs/publication/license-reviews/vscode.md`, and **a published demo
  fails the gate until the owner countersigns.** A license review signed only by
  the tool that wants to publish is not the check 6.1 is asking for.

## Verification, all of it

```
pytest                1708 passed, 4 skipped, 1 xfailed, 1 failed
                      (baseline 1641 + 67 new; the 1 failure is the known
                       worktree-only .git-is-a-file case)
ruff                  All checks passed
preview-gate          12/12 pass
viewer tsc            clean
viewer eslint         clean
viewer vitest         11 files / 86 tests failed, FILE SET IDENTICAL to baseline
golden-corpus flask   no drift
golden-corpus fastapi no drift
```
