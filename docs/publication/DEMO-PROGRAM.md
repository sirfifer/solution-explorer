# The SysCorpus demo program

Status: PLAN, awaiting owner decisions (written 2026-08-18). This is the
"showcase program" that `DISCLOSURE-POLICY.md` has referenced since 2026-07-21
without one existing. It defines what we publish, in what order, how it stays
current, and how each run feeds fixes back into the product.

Domain: `syscorpus.com` (owner also holds the `.org`). Commercial intent is
explicit: the product is being built to sell, so this program is both a test
harness and the shop window a buyer will look at first. That double duty drives
almost every judgement call below.

---

## 1. Fresh audit: what already exists

The owner's instinct was right. Most of the machinery exists and is scattered
across four campaigns. What is missing is the program itself: the list, the
cadence, the local execution path, and the feedback loop.

| Asset | Where | State | Reusable as-is? |
|---|---|---|---|
| Showcase disclosure policy (consent, triage, wait states, publish, record) | `docs/publication/DISCLOSURE-POLICY.md` | Adopted 2026-07-21 | Yes, verbatim |
| Maintainer outreach email | `docs/publication/maintainer-outreach-email.md` | Written | Yes |
| Publication metadata (`publication.json`): schema, two templates, unofficial framing, provenance stamping | `docs/publication/` | Design approved; viewer components present (`PublicationBanner`, `PublicationFooter`, `utils/publication.ts`) | Yes, verify rendering at pre-flight |
| Installation registry | `DEPLOYMENTS.md` | Two rows, both UnaMentis | Extend, do not replace |
| Pinned-clone harness: lock file, gitignored cache, fetch/generate/baseline/check/parity | `scripts/golden-corpus.py`, `tests/golden/*/corpus.lock` | Built for Flask and FastAPI | Copy the idiom, different policy (see 4.1) |
| Projection diff, human and CI readable | `scripts/projection-diff.py`, `scripts/blue-green-diff.py` | Built (cards G1, G3) | Yes, this is the week-over-week signal |
| Headless enrichment with cost ceiling, staleness-scoped `--update`, quality gate | `analyze.py enhance`, `analyzer/enrich/` | Built (P7-2) | Yes |
| Multi-repo solution composition | `analyze.py --solution`, `analyzer/solution/` | Built (M1), no cross-repo edges | Yes, with one blocker (see 1.1) |
| Cloudflare Pages deploy | `action.yml` via `wrangler-action`; `wrangler` present locally | Built for CI | Needs a local path (see 1.1) |
| SBOM, CRA readiness artifact, front door (`ai.json`, `llms.txt`), coverage ledger | analyzer | Built | Yes, these are what "full class" means |
| The card that anticipated this | `docs/remediation/TASKS.md` P9-1 "Large-repo public demos" | TODO, unelaborated | This plan elaborates it |
| Candidate projects, mentioned in passing | `REGRESSION-STRATEGY.md`, TASKS.md | vscode as a scale benchmark; Flask and FastAPI as frozen corpora; NestJS and Alamofire as "later"; Django excluded on size | Starting input, not a plan |

### 1.1 The gaps this plan has to close

1. **No local deploy path for a repo we do not own.** `/install` says "into a
   repo you control" and works by writing a workflow into the target repo.
   `/ai-assist` deploys by committing the output INTO the analyzed repo. Neither
   works for VS Code. The demo program needs the inverted path: analyze a local
   clone, deploy from our side, never touch upstream.
2. **No local cadence.** Every existing refresh path is a GitHub Action fired by
   a merge. Nothing runs on a schedule on our own hardware.
3. **The license review the disclosure policy promises does not exist.** Section
   1.2 below plus the per-demo gate in 6.1 is that review.
4. **Multi-repo emits no unified coverage ledger** (TASKS.md P4-7), so a
   multi-repo demo would show "Coverage unavailable for this dataset". Honest,
   but it blocks the one demo that shows off the product's differentiator.
5. **No findings loop.** Discoveries currently land in TASKS.md prose by hand.
   GitHub Issues on `sirfifer/solution-explorer` is effectively unused (one
   issue, from March).
6. **No classification accuracy check.** The comprehension study's worst trust
   defect was S2, confident misclassification. Enrichment quality is scored;
   deterministic classification is not. A weekly public demo will surface this
   class constantly and we have no instrument for it.
7. **Java, Kotlin, C, C++, C#, Dart are detection-plus-metrics only.** Full
   parsing covers Swift, Python, Rust, TypeScript/JavaScript, Go, Ruby. This is
   the single largest capability wall and it decides the whole shape of the list.

### 1.2 One legal point that is easy to miss

The viewer renders upstream README, CLAUDE.md, and documentation excerpts inside
the detail panel, and shows evidence snippets with file and line. A deployed
demo therefore redistributes third-party copyrighted text, not only facts about
it. MIT, BSD, and Apache-2.0 all permit that and all require the notice to
travel with it. So every published demo must ship the upstream `LICENSE` in the
deployed bundle and name it in `publication.json`. This is cheap to do and
expensive to retrofit during a buyer's diligence.

---

## 2. The organizing idea: two tracks, one program

The owner's instruction is to find the hard things and hit them head on,
expecting to fail at first. VISION.md's no-theater rule says we must never ship
a surface that implies capability we lack. Both are right, and they collide the
moment a Java monorepo renders as a blank map on a public URL.

The resolution is two tracks with an explicit graduation gate.

**Track A, published demos.** Live on `syscorpus.com`, refreshed weekly, listed
publicly. A demo reaches Track A only when it fairly represents its subject.

**Track B, capability-forcing targets.** Local or gated preview only. Chosen
precisely because they break the tool. Refreshed on demand, not weekly. Their
job is to generate findings and justify capability work. They graduate to Track
A when they pass the same gate as everyone else.

Graduation gate (all must hold):

- Coverage ledger complete, zero unaccounted rows.
- Detect-only languages under 25 percent of counted code lines. Above that the
  map is mostly a file listing and publishing it is theater.
- Enrichment quality at or above threshold (85), zero failed partitions.
- Front door agrees with the manifest (the S3 truthfulness check).
- Classification sample audit at or above its floor (instrument to be built, 5.3).
- License review passed and upstream LICENSE shipped (1.2).
- Sensitivity triage clean, or outreach completed per DISCLOSURE-POLICY.md.

This split is the most commercially important decision in the plan. A weak map
of a famous repository on a public URL is the fastest available way to destroy
the perceived value of the product. Track B is where we take the risk; Track A
is where we take the credit.

---

## 3. The list

### 3.1 Selection criteria

Every candidate is judged on which specific thing it breaks, not on how
impressive it sounds. The stress axes:

| Axis | What it tests |
|---|---|
| **Scale** | Lines and files, wall time, memory, store size |
| **Breadth** | Component count, which stresses aggregation, search, and the viewer |
| **Language depth** | Full-parse tier versus detection only |
| **Structural exotica** | Monorepo that is really multi-repo, symlinks, vendored trees, generated code |
| **Multi-repo solution** | The product's actual differentiator |
| **Data and API surface** | Entities, endpoints, capabilities, rules |
| **Supply chain** | SBOM breadth, pinning, transitive depth |
| **Consent risk** | Corporate or foundation governance versus a single maintainer |

Recognizability matters too, but only as a tie-breaker. A demo nobody recognizes
proves the same capability and sells nothing.

### 3.2 Wave 1, start here (three demos)

Three subjects, three different stress axes, three different full-parse
languages, all permissive licenses, all foundation or corporate governance so
consent friction is minimal.

| # | Subject | Language / License | Axis | Track |
|---|---|---|---|---|
| 1 | **microsoft/vscode** | TypeScript, MIT | Scale, TS depth, UI surface | A |
| 2 | **kubernetes/kubernetes** | Go, Apache-2.0 | Structural exotica, supply chain, API surface | A, expect gate failures first |
| 3 | **home-assistant/core** | Python, Apache-2.0 | Breadth, plugin architecture | A, expect gate failures first |

**1. VS Code.** Start here because the risk of an embarrassing first result is
lowest and the payoff is highest. We have already measured it: 16,482 files,
about 3.47M lines, 152 seconds cold, 121 warm, 1.9 GB peak, 420 MB store, with a
complete coverage ledger. README already cites that number as a claim, so this
demo makes a published claim independently verifiable by anyone. Expect trouble
in `src/vs/**`, which is layered folders rather than package-per-directory, so
component discovery may produce a shallow or lopsided tree; `extensions/` is
roughly a hundred small packages, which is a real aggregation test; and the
Electron main, renderer, and worker split is a relationship story our port and
URL heuristics will not see. Every one of those is a finding worth having.

**2. Kubernetes.** This is the deliberate hard one, and the most valuable single
entry on the list. `staging/src/k8s.io/*` holds real published modules that are
symlinked into `vendor/`, which makes it a monorepo that genuinely is a
multi-repo solution: exactly the shape the product claims to be built for.
Around it sit a huge vendored tree (does the ledger classify vendored correctly,
does the SBOM see it), heavy generated code (`zz_generated.*`, protobufs), and
API groups and versions that should light up the Data and Capability lenses.
Expected failures: symlink handling in the walker, including the risk of double
counting or cycles; vendored versus first-party classification, where the S8
line-count taxonomy work applies directly; generated-code bucketing; and a
component count in the thousands. For an enterprise buyer this is also the most
credible demo on the list.

**3. Home Assistant Core.** Over two thousand integration packages under
`homeassistant/components/`, each with a `manifest.json`. Nothing else in the
open-source world stresses component breadth like this, and breadth is exactly
where the last two campaigns of work went (importance ranking, node budget,
aggregation, snap zoom). Expected failures: one enormous flat drill level, search
index size, detail shard count against hosting limits, and enrichment cost at
two thousand components. Its audience reach is also unusually wide, including
non-developers, which is the Doug persona the stakeholder views target.

### 3.3 Wave 2 (three, each unlocks something)

| # | Subject | Language / License | Axis | Track | Unlocks |
|---|---|---|---|---|---|
| 4 | **denoland/deno** | Rust + TypeScript, MIT | Polyglot across two full-parse tiers | A | Rust at real scale; one story across a Rust core and a TS surface |
| 5 | **Supabase** (`supabase/supabase`, `postgrest/postgrest`, `supabase/realtime`, `supabase/storage-api`, `supabase/auth`) | TS, Go, Haskell, Elixir; Apache-2.0 and MIT | True multi-repo solution, data layer, declared language gaps | B until the multi-repo ledger lands, then A | The differentiator demo; forces P4-7 (unified multi-repo coverage ledger) |
| 6 | **spring-projects/spring-boot** | Java, Apache-2.0 | Language tier wall | B, indefinitely | Justifies and specifies a Java tree-sitter tier |

Supabase deserves a note. Two of its members are Haskell and Elixir, neither in
any tier, so the ledger will declare a large honest gap. That is the right kind
of failure to publish, because it is declared rather than hidden, and it is the
clearest possible argument for the coverage ledger as a feature. But it cannot
publish until multi-repo emits a unified ledger, so it sits on Track B and pulls
that deferred card forward.

Spring Boot is on the list precisely because it will fail. Java is the largest
enterprise language we cannot parse, and a buyer will notice that in the first
five minutes. A metrics-only map of a forty-module Java monorepo is not
publishable under the theater gate, so its entire purpose is to make the Java
tier concrete: what breaks, what a tier would have to produce, and what it buys.

### 3.4 Wave 3, the succession (not exhaustive, by design)

| # | Subject | Language / License | Why it is on the list |
|---|---|---|---|
| 7 | **redis/redis** | C, BSD-3 | Forces a C tier at a tractable size (~200k lines) instead of starting with a kernel |
| 8 | **rails/rails** | Ruby, MIT | Monorepo-of-gems shape; ActiveRecord for the Data lens; Ruby at scale, which today is proven only by one misclassified file in the UnaMentis demo (S2) |
| 9 | **Alamofire** or **pointfreeco/swift-composable-architecture** | Swift, MIT | Swift on code we did not write. Today Swift is proven only on our own project, which is a weak proof |
| 10 | **dotnet/runtime** | C#, MIT | Second language wall plus the largest scale test after Kubernetes. Long horizon, Track B |
| 11 | A multi-repo "golden solution" | To choose | REGRESSION-STRATEGY.md already calls for one once M1 matures |

Eight to twelve published demos is a rich shop window. Past that the marginal
demo teaches nothing new and every one carries a weekly refresh, a validation
gate, a findings triage, and a license review forever.

### 3.5 Deliberately excluded, and why

- **Linux kernel, Chromium.** Tens of millions of lines of C and C++ with no
  tier and build systems that defeat component discovery. All cost, no story,
  until a C tier exists and scale is proven at Kubernetes size.
- **Django.** Already excluded as a golden corpus on size, and as a demo it is
  redundant with Home Assistant for Python and Rails for the framework-monorepo
  shape.
- **AGPL and SSPL subjects** (Grafana post-relicense, MongoDB, Signal clients).
  Not because structural analysis infringes, but because a company we intend to
  sell gains nothing from a license-adjacent argument on its public marketing
  surface. Fine as Track B locals, never Track A.
- **Single-maintainer projects.** DISCLOSURE-POLICY principle 2 means the
  friction cost is highest exactly where the human cost is highest. Public demos
  prefer foundations and corporations.
- **Security-sensitive subjects** (crypto libraries, auth servers). Private
  preview path only, per the policy's own triage rule.
- **A fifty-project ambition.** Rejected on the owner's instruction and on the
  arithmetic above.

### 3.6 What "full class representation" means, per demo

A demo is not done until all of this is true. This is the checklist the harness
enforces:

split-mode projection with per-component detail shards; complete coverage
ledger with the badge visible; AI enrichment at or above threshold with
provenance; SBOM; CRA readiness artifact; machine front door (`ai.json`,
`llms.txt`) that agrees with the manifest; search index including endpoints;
`publication.json` with showcase framing, exact commit, and snapshot date;
upstream LICENSE shipped; and a recorded run report.

---

## 4. Execution: all local, on the Studio

The owner's read is correct. There is no reason to spend GitHub Actions minutes
on this, we have a permanent machine, and the codebases are small compared to
what that machine already stores. Everything below runs locally and is
committed to this repo so it is reviewable and reproducible.

### 4.1 The registry

One committed file per demo, `demos/registry/<slug>.json`, deliberately shaped
like `corpus.lock` so there is one idiom in the repo for "a pinned outside
codebase we care about". The difference is policy: a golden corpus is FROZEN so
that any diff is attributable to our engine, while a demo TRACKS upstream so it
is never stale. Same mechanics, opposite intent, and they must not be merged
into one thing.

```json
{
  "slug": "vscode",
  "subject": {
    "name": "Visual Studio Code",
    "repo": "https://github.com/microsoft/vscode.git",
    "license": "MIT",
    "governance": "corporate"
  },
  "track": "published",
  "policy": { "follow": "default-branch", "pin": null, "exclude": [] },
  "hosting": { "cf_project": "syscorpus-vscode", "url": "https://vscode.syscorpus.com" },
  "cadence": "weekly",
  "budget": { "max_cost_usd": 5.0, "max_wall_minutes": 45 },
  "gates": { "coverage": "complete", "max_detect_only_line_share": 0.25, "min_enrichment_score": 85 },
  "consent": { "required": false, "state": "n/a", "contacted": null }
}
```

`follow` is one of `default-branch`, `latest-tag`, or `pinned`. Whatever it
resolves to, the harness records the exact SHA it analyzed and stamps it into
`publication.json`, so provenance is exact even when the policy is loose.

### 4.2 The harness

`scripts/demo-site.py`, subcommands mirroring `golden-corpus.py`:

| Subcommand | Does |
|---|---|
| `list`, `status` | Registry contents, last run per demo, what is due |
| `fetch <slug>` | Clone or fetch into `~/dev/.demo-corpus/<slug>`, resolve and record the SHA |
| `analyze <slug>` | v2 split projection with a persistent per-demo store, so refreshes are warm and incremental |
| `enhance <slug>` | `analyze.py enhance --update` with the per-demo cost ceiling |
| `validate <slug>` | The 3.6 checklist plus the 2 graduation gates; exits non-zero on any failure |
| `diff <slug>` | Projection diff against last week's build (blue versus green) |
| `deploy <slug>` | `wrangler pages deploy` to the demo's own Pages project |
| `report <slug>` | Run record, JSON and markdown |
| `findings <slug>` | Turn machine-gate results into deduplicated GitHub issues (section 5) |
| `refresh <slug>` | The whole chain, stopping at the first gate failure |
| `refresh --due` | Every demo whose cadence is up |
| `hub` | Regenerate the hub site from the registry and the run records |

Nothing here is new capability. It is orchestration over CLIs that already
exist, which is why the estimate in section 8 is days and not weeks.

### 4.3 Cadence

A `launchd` user agent on the Studio, not cron, because launchd survives reboots
and does not need the Full Disk Access dance. One demo per night rather than all
on one night, so a failure is isolated, the machine is never saturated, and a
bad week is one demo stale rather than all of them. Each demo still lands on a
weekly cycle. `refresh --due` picks whatever is up.

Two honest operational notes:

- **Enrichment authentication.** `analyzer/enrich/engine.py` invokes the model
  through the `claude` CLI (`claude -p --output-format json`). An unattended
  weekly run therefore depends on a logged-in Claude Code session on that
  machine, and it draws on the owner's subscription usage rather than a separate
  billed key. A credential expiry becomes a silent weekly failure. Section 9,
  decision 4 puts an API-key invoker on the table, which also makes per-demo cost
  attributable, which matters for the unit-economics story in a sale.
- **Failure must be loud.** A refresh that fails a gate must notify, not just
  write a log nobody reads. The hub shows each demo's last successful refresh
  date, so a stalled demo is visible publicly, which is its own forcing function.

### 4.4 Hosting layout

Recommended: one Cloudflare Pages project per demo, on its own subdomain, plus a
separate small hub project.

- `syscorpus.com` stays free for the commercial site.
- `demos.syscorpus.com` is the hub, generated from the registry.
- `vscode.syscorpus.com`, `kubernetes.syscorpus.com`, and so on, one per demo.

The decisive argument is a measured limit, not taste. Cloudflare Pages allows
20,000 files per site on the free plan and 100 projects per account. Split mode
emits one detail shard per component, so a single shared project would pool every
demo against one 20,000-file budget, and Home Assistant alone could consume a
large share of it. Per-demo projects give each demo its own file budget, its own
deploy history for rollback, independent refresh, and a broken demo that cannot
take the hub down. The cost is one DNS record per demo, which is trivial.

The hub is generated, never hand-maintained, so it cannot go stale: subject,
license, upstream commit, snapshot date, size and coverage stats, last refresh,
and a link. It also carries the program's honest framing, and the feedback path
in section 5.4.

### 4.5 Freshness honesty

`publication.json` carries `update_policy: periodic`, the exact commit, and the
snapshot date, all stamped by the harness. The S8 lesson applies directly: when
upstream has not changed since the last refresh, the demo says so ("source
unchanged since <date>") rather than wearing an old date silently and reading as
a broken pipeline.

### 4.6 Pre-flight measurements needed before any of this is committed to

One day of measurement, no publishing, answers the questions this plan is
currently guessing at:

1. Component count and detail shard count for each Wave 1 subject, against the
   20,000-file ceiling.
2. Wall time, peak memory, and store size per subject on the Studio.
3. Detect-only language share of lines per subject, against the 25 percent gate.
4. A real enrichment cost measurement per subject via `enhance --dry-run`, since
   the recorded figures range from fractions of a dollar to a few dollars and
   none of them are at Home Assistant's component count.
5. Whether `wrangler pages deploy` of prebuilt assets consumes the 500 per month
   build quota or bypasses it as a direct upload.
6. Disk footprint for clone plus store per subject, to size the total.

---

## 5. The continuous-improvement loop

The owner's framing is exactly right and is the most valuable part of this
program: every generation, and especially every AI enhancement, is an
opportunity to catch what is not where it needs to be. The loop has to be
mechanical or it will not survive contact with a busy week.

### 5.1 Where findings come from

**Machine gates, computed every refresh.** All of these are cheap and
deterministic:

- Any `unaccounted` ledger row. Hard failure, blocks publish.
- `excluded:unsupported_extension` file share, and detect-only language share of
  lines. A capability finding, and the theater gate.
- Zero-symbol components in a full-parse language. A parser finding.
- Orphan share: components with no relationships. A relationship-inference finding.
- Enrichment: failed partitions, quality score, staleness surviving a refresh.
- Front door versus manifest disagreement. The exact S3 class.
- Shard count and manifest size against hosting limits. A scalability finding.
- Wall time, peak memory, and store size versus last week. A performance finding.

**Projection diff.** Week-over-week deltas that do not correspond to the
upstream commit range are our engine changing, not the subject changing. That is
the blue and green signal REGRESSION-STRATEGY.md already specifies, applied
weekly instead of on demand.

**Representation audit.** The P9-0 dogfood gate charter applied to a demo: does
this projection fairly represent the project? The comprehension study did this
by hand for UnaMentis and found nine defects. Cheap recurring version in 5.3.

**Human and outside feedback.** The owner browsing, and the public feedback path
in 5.4.

### 5.2 Where findings go

GitHub Issues on `sirfifer/solution-explorer`, filed by the harness, which is
the owner's proposal and the right call: it is a queue with notifications, it
dedupes, and TASKS.md is already 2,869 lines of campaign narrative.

One refinement, because two trackers always drift. Define the seam:

- **Issues are the inbox.** Machine-filed, deduplicated, cheap, disposable.
- **TASKS.md stays the campaign tracker.** When an issue becomes real work, it
  gets a card in TASKS.md and the issue links to it. The card is the plan of
  record; the issue is the receipt.

Mechanics that make this survive weekly repetition:

- Every machine-filed issue body carries a stable fingerprint,
  `demo-finding:<slug>:<check>:<hash>`. The next run comments on the existing
  issue instead of opening a duplicate.
- When a check goes green, the harness closes the issue with a comment naming
  the run that cleared it. Never a silent close.
- Labels: `demo-finding`, `demo:<slug>`, and a capability label
  (`capability:language-tier`, `capability:coverage`, `capability:enrichment`,
  `capability:classification`, `capability:viewer`, `capability:performance`).
- Severity from the gate: a publish-blocking gate opens a blocker, everything
  else opens a normal finding.

### 5.3 The one new instrument this program needs

A **classification accuracy audit**. Today enrichment quality is scored and
deterministic classification is not, and misclassification (S2) was the single
worst trust defect the comprehension study found: one wrong "Remote Log Server"
cost ten minutes and permanent suspicion of every other label.

Shape: sample N components per refresh, compare each declared fact (type,
framework, port, endpoints, language) against its own recorded evidence, and
score. Partly mechanical (does the evidence support the claim at all) and partly
an adjudicated pass in the style of `score-ai-enhancement-quality.py`. Output is
a per-demo accuracy number tracked over time, plus a finding per
misclassification. This is the instrument that turns "the map must never lie"
from a principle into a measurement, and a demo program without it will publish
the same class of defect every week without noticing.

### 5.4 Public feedback path

The owner wants outside feedback. The hub carries one honest invitation that
lands somewhere useful:

- A "something wrong here?" link on every demo, pointing at a prefilled GitHub
  issue template (`demo-feedback`) that captures the demo slug, the component,
  and what looks wrong.
- The viewer's existing review and annotation export already produces a
  structured report pairing human intent with machine context. The hub should
  teach that as the high-fidelity path, because it is genuinely good and it costs
  us nothing.

---

## 6. Legal, consent, and the diligence trail

A buyer's diligence will read the public surface first. Everything here is cheap
now and expensive to retrofit.

### 6.1 Per-demo license review (the missing artifact)

Recorded in the registry entry and checked by `validate`:

1. Identify the upstream license and confirm it permits redistribution of the
   documentation text and excerpts the viewer renders (1.2).
2. Ship the upstream LICENSE in the deployed bundle and name it in
   `publication.json`.
3. Confirm no copyleft obligation attaches to our viewer bundle. Our own code is
   FSL-1.1-ALv2; keep subject content and tool code cleanly separated in the
   bundle.
4. Trademark: use plain text names, never logos or wordmarks, and keep the
   unofficial and not-affiliated framing the showcase boilerplate already
   carries.
5. Record the reviewer and the date.

### 6.2 Consent

DISCLOSURE-POLICY.md applies unchanged, and for a company being sold, the
consent records become an asset rather than a chore: a documented, respectful
outreach trail is exactly what a careful acquirer wants to see attached to a
public marketing surface built on other people's code.

---

## 7. Cost, capacity, and what can go wrong

| Resource | Estimate | Note |
|---|---|---|
| Disk per large demo | roughly 1 to 3 GB clone plus store (VS Code store measured at 420 MB) | Ten demos land in the tens of GB. Not a constraint on this machine |
| Wall time per refresh | 3 to 20 minutes warm for Wave 1 subjects (VS Code measured 121 s warm for analysis alone) | Staggered nightly, so never contended |
| Enrichment, first full run | fractions of a dollar to a few dollars per demo at recorded rates | Home Assistant at 2,000+ components is the unknown; measure at pre-flight |
| Enrichment, weekly `--update` | near zero | Staleness-scoped to what upstream actually changed |
| Cloudflare Pages | free plan: 20,000 files per site, 25 MiB per file, 100 projects, 500 builds per month | Direct uploads and the build quota need confirming (4.6 item 5) |

Risks worth naming now:

- **Claude CLI credential expiry** silently breaks weekly enrichment (4.3).
- **Upstream force-push or repository rename** breaks a fetch. The harness must
  fail loudly, not analyze a stale clone.
- **A subject grows past a hosting limit** between refreshes. The shard-count
  gate catches it before deploy rather than after.
- **Publishing a weak map** on a famous repository. Mitigated by the Track A and
  Track B split, which exists for exactly this.

---

## 8. Sequenced work plan

| Phase | Work | Effort | Done means |
|---|---|---|---|
| **D0** | Pre-flight measurements (4.6) on all three Wave 1 subjects. No publishing | 1 day | Real numbers for shard count, wall time, detect-only share, cost, disk. Hosting layout confirmed against them |
| **D1** | Registry, harness, hub generator, launchd schedule. VS Code end to end and public | 4 to 6 days | `vscode.syscorpus.com` live, hub live, two consecutive automated weekly refreshes proven, run records committed |
| **D2** | Kubernetes and Home Assistant onboarded | 3 to 5 days | Both analyzed and validated. Gate failures expected and filed as findings, not hidden. Publish whichever passes |
| **D3** | Findings loop: issue filer with fingerprints, labels, auto-close; classification accuracy audit (5.3) | 2 to 3 days | A refresh files, updates, and closes issues without duplicates. Every demo carries an accuracy number |
| **D4** | Wave 2: Deno published; Spring Boot onboarded on Track B; multi-repo unified ledger (P4-7) then Supabase | 1 to 2 weeks plus the ledger card | Deno public. A written Java tier specification derived from the Spring Boot failure. Supabase publishable |
| **D5** | Wave 3 and the language tiers the findings justify, in the order the findings justify them | Ongoing | Each new tier is opened by a Track B demo and closed by that demo graduating to Track A |

Per-demo onboarding after the harness exists is roughly half a day to a day:
pre-flight, first full enrichment, license review, sensitivity triage, deploy.

---

## 9. Decisions needed

Four, each with options and a recommendation. Everything else in this plan is a
recommendation I will execute as written unless told otherwise.

### D1. Wave 1 composition

| Option | For | Against |
|---|---|---|
| **A. VS Code, Kubernetes, Home Assistant (recommended)** | Three axes, three full-parse languages, three permissive licenses. One safe opener and two genuinely hard ones | Two of the three will fail their first gate. That is the point, but it means Wave 1 publishes one demo before it publishes three |
| B. VS Code plus Deno plus Rails | Almost certain to publish all three quickly. Good breadth of language | Teaches much less. None of them stress structure or breadth, which is where the real gaps are |
| C. VS Code and Kubernetes only | Focus. Half the onboarding cost | Skips breadth, which is exactly what the last two campaigns of work targeted |
| D. Kubernetes first, alone | Hits the hardest thing immediately | High chance of weeks with nothing public, which wastes the shop-window value |

### D2. Hosting layout

| Option | For | Against |
|---|---|---|
| **A. One Pages project and subdomain per demo, separate hub (recommended)** | Per-demo file budget against the 20,000 limit, independent refresh and rollback, one broken demo cannot break the hub | One DNS record and one project per demo |
| B. One project, demos as subdirectories | One project, one DNS record | All demos share one 20,000-file budget, every refresh redeploys everything, one bad build breaks every demo |
| C. Per-demo projects under `demos.syscorpus.com` paths via a router Worker | Pretty URLs, still isolated | A Worker in the path is another moving part to maintain and debug |

### D3. Findings inbox

| Option | For | Against |
|---|---|---|
| **A. GitHub Issues as inbox, TASKS.md as campaign tracker, explicit seam (recommended)** | Notifications and dedup where you already look; TASKS.md stays the plan of record | Two places to look, mitigated by the seam rule in 5.2 |
| B. GitHub Issues only | One place | TASKS.md is the campaign's memory and carries gate records; abandoning it loses real history |
| C. TASKS.md only | One place, current practice | No notifications, no dedup, and a weekly machine process would bloat it fast |

### D4. Enrichment authentication for unattended runs

| Option | For | Against |
|---|---|---|
| **A. Add an API-key invoker alongside the CLI (recommended)** | Scheduled runs stop depending on an interactive login; per-demo cost becomes attributable, which is a unit-economics fact worth having for a sale | Half a day of work, plus a key to manage and a real bill to watch |
| B. Keep the `claude` CLI | Zero work | A credential expiry becomes a silent weekly failure, and demo cost is mixed into personal subscription usage |
| C. Keep the CLI and add a liveness pre-check | Cheap, catches the failure early | Still no cost attribution, still tied to one machine's login |

---

## 10. The commercial thread

The owner's target is a sale at no less than a few hundred thousand, possibly
more, and wants the value estimate revisited as things progress. Two things
belong in this plan and no more.

**What this program does for value.** For a solo-built developer tool with no
revenue, the value drivers a buyer actually weighs are: a demonstrable technical
moat, evidence it works on real code at real scale, clean IP, and some market
signal. This program is the direct instrument for the second and part of the
fourth, and the diligence trail in section 6 protects the third. Weekly
automated refresh with gates and provenance also evidences operational maturity,
which is the difference between a prototype and an asset.

**What it risks.** The same surface that proves capability can disprove it.
Publishing a blank Java map or a lopsided VS Code tree on a public URL under our
own domain is the cheapest available way to lower the number. That is why the
graduation gate in section 2 is a hard gate and not a guideline.

**The valuation thread itself** should be its own recurring artifact, not folded
into this one: a short `docs/commercial/VALUATION-SNAPSHOT.md`, updated at each
milestone, naming the drivers, the current evidence for each, the comparables,
and an honest range with its assumptions. I have not written it here because it
was not this task, and because doing it properly needs its own research pass on
comparables and on what an acquirer of a tool like this actually pays for. Say
the word and it becomes the next piece of work.
