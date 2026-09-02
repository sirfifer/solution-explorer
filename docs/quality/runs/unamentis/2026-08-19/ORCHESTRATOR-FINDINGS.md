# Orchestrator findings, N1 calibration run

Findings the orchestrator established independently, with root causes, during
verification. Separate from persona findings. Convention: **VERIFIED** means a
root cause was found; **CONFIRMED** means reproduced or corroborated only.

## O1. Documentation is indexed by filename only. Its content is not searchable. VERIFIED

**Measured across the published search index:**

| ref_kind | entries | empty text | share empty |
|---|---:|---:|---:|
| component | 254 | 237 | 93.3% |
| file | 1,249 | 570 | 45.6% |
| symbol | 12,693 | 7,850 | 61.8% |

**Markdown files: 233 indexed, 233 with empty text, 0 with text.** No exceptions.

The subject carries 130,253 lines of documentation against 342,177 lines of
code, a density of 0.38 doc lines per code line. That corpus is the richest
source of architectural truth about the subject, and none of it is reachable by
search. Content is reachable only by browsing to the owning component, which
requires already knowing which file to open.

**Consequence, demonstrated twice.** The subject's own infrastructure document
records that its production backend runs on one laptop and lists, verbatim,
"Single point of failure" among that host's disadvantages. The phrase appears
**nowhere in the entire published payload**. The document is present in the
index as a bare file entry with `"text": ""`. The 2026-08-17 executive persona
missed this fact, and so did the 2026-08-19 executive persona, independently and
for the same structural reason.

This is the highest-value fact in the subject for the audience the product most
wants to serve, and the tool cannot lead anyone to it.

**Not scored against either persona.** The answer key requires this to be
recorded as a finding regardless of persona score, and it is a product gap
rather than a reviewer failure.

**Qualification, stated because it cuts against the finding.** Some
documentation prose does reach the published payload by other routes: the
manifest carries doc-derived content including a deployment comparison naming
"MacBook Pro M4 Max" with availability "Intermittent" against a Proxmox option
at "24/7". So the underlying risk is not wholly absent from the data. It is
absent from search, which is the route a reviewer actually takes.

## O2. The external dependency count is incomplete detection presented as a complete count. VERIFIED

**Root cause.** `analyzer/constants.py:213-235`, `EXTERNAL_CLOUD_APIS`: a
hardcoded dict of 18 literal domains. Detection requires the literal domain
string in a URL-shaped context, by two detectors, `scanner.py:1536-1580` and
`derive/relationships.py:688-702`. The viewer aggregates without further
filtering (`viewer/src/lenses/inventory.ts:99-102`).

The dict is a generic template, not a definition curated for this subject: it
also carries Stripe, Twilio, SendGrid, Firebase, GitLab and Slack, none of which
are relevant here.

**What that produces on this subject:**

- **GitHub is counted as an external dependency of a tutoring application**
  because a CI helper script under `unamentis/scripts` contains
  `https://api.github.com`. Not a runtime dependency.
- **Unleash and LiveKit are absent from the dict entirely** despite being real
  runtime integrations. Evidence in the published data itself: `UnleashClient`,
  an `unleash-proxy` docker service, `UnleashProxyResponse`, and config keys
  `.liveKit` and `.liveKitSecret`.
- **Google AI and AssemblyAI are in the dict but were not detected**, though the
  subject demonstrably uses them, including a file named
  `AssemblyAISTTService.swift`.
- **Ollama, Piper and Chatterbox cannot ever appear**, being self-hosted with no
  fixed domain. That is an artifact of the matching mechanism, not a policy.

**Why it matters more than a miscount.** The figure is presented as a count,
"5 external dependencies", which is a definite claim. The underlying operation
is "whatever literal domain strings happened to match". A count asserts
completeness that the method cannot support. This is the exact failure mode the
product exists to avoid.

**Corroboration.** Found independently three ways: the 2026-08-19 P1 persona
noticed the tool's own Inventory lens and Flow narrative disagreeing and
scrupulously recorded it as unverified rather than false; the difficulty-profile
measurement independently found exactly five; and reading the subject's source
found four more the tool never mentions.

## O3. Symbol search discards symbol targets the data provides. VERIFIED

**Root cause.** `viewer/src/components/SearchOverlay.tsx:86-113`, `handleSelect`.
The symbol branch resolves `architecture?.symbols.find(s => s.id === result.id)`.
In split mode that collection holds only components whose detail has already
been fetched, so for any symbol in an unopened component the lookup misses and
the code falls through to `navigateToComponent(result.componentId)`, landing on
the parent and stopping. Nothing re-resolves the symbol once its detail loads.

**The data is sufficient.** The shard entry carries the correct `ref_id`, and
the owning component's detail file carries `line` and `end_line` for that same
id: `AudioWebSocketHandler` at lines 20 to 410, `IdleManager` at 131 to 141. The
targeting information exists one hop away and is discarded.

**Reproduced by a persona independently.** The 2026-08-19 P1 hit this on exactly
those two symbols, across separate attempts, and worked around it via the Files
tab.

**Note.** The fallback is documented in a source comment as deliberate, so this
is a design shortcut whose user-visible effect is an advertised path that does
not work, rather than an unknown bug.

## O4. The interface advertises coverage it cannot deliver. VERIFIED

The coverage ledger does not exist in this dataset: no `coverage` key in the
manifest, `present: false` in `ai.json`, and `/architecture/coverage.json`
resolves to the SPA shell on the live origin.

`viewer/src/components/CoverageBadge.tsx:338-354` hides the badge only when the
dataset has no `repositories`. This dataset has one repository entry, so
`multiRepo` is true and the badge renders the visible string **"Coverage
unavailable for this dataset"**. Surrounding surfaces keep treating coverage as
a live feature: a Testing tab (`DetailPanel.tsx:254`), a per-transcript Line
Coverage bar (`DetailPanel.tsx:2007-2024`), a node tooltip reading
"N tests (X% coverage)" (`ComponentNode.tsx:1131-1133`), and the copy "The
complete list is in the coverage ledger." (`InventoryPanel.tsx:260-261`),
pointing at a ledger that does not exist.

The 2026-08-17 P1 persona hit the same string, so this is unchanged since the
baseline.

## O5. A hypothesis I raised and then disproved, recorded so it is not re-raised

The 2026-08-17 personas referred to "the tour", and the current dataset has no
`tours` key, which looked like a capability regression. It is not: the baseline
dataset had no `tours` key either. Whatever they called "the tour" was the
onboarding summary, not the Tours feature. No regression.

## O6. Snapshot freshness improved materially

The baseline persona complained that the snapshot was 26 days old, generated
2026-07-22 and viewed 2026-08-17, and treated the staleness as a trust spender.
The dataset under review was generated 2026-08-19T02:35Z and reviewed the same
day.

## O7. A persona's confident negative claim was false. VERIFIED, and it is the most important instrument finding of the run

**The claim.** 2026-08-19 P1, recorded as a blocked path: "Graph view toggle.
Present in the DOM/breadcrumb, never had a clickable bounding box in any state I
reached. **Never got a node-and-edge visualization to render.**"

**It is false.** P1's own screenshot `31-root-view.png`, taken during the very
attempt that produced that conclusion, shows a fully rendered node-and-edge
graph: nodes for `server-manager`, `unamentis-web-client`, `web`,
`unamentis-management` and `usm-core`, connected by labelled edges reading
`WebSocket` and `HTTP REST :4242`, with ports `:8766` and `:8767` on the nodes.

**Source confirms it could not have been otherwise.** `<ArchitectureGraph />` is
rendered unconditionally inside `<main>` at `viewer/src/App.tsx:986-997`. There
is no view mode in which it is absent.

**The first half of the claim is explicable and not a defect.** The
`Tree / Graph` buttons P1 found in the DOM are a mobile bottom-navigation bar
(`App.tsx:1081-1095`) that merely toggles the sidebar. At desktop width they are
present in the DOM but not visible, which is precisely "no clickable bounding
box". P1 diagnosed a real DOM observation correctly and drew a wrong conclusion
from it.

**Why this matters beyond one score.** An agent persona looked directly at a
working visualization, screenshotted it, and reported that it did not exist.
That is a failure mode a human persona does not have, and it is invisible unless
the orchestrator opens the screenshots. It means:

1. **Persona blocked-path claims cannot be taken at face value.** Every one must
   be checked against the source or the persona's own evidence before it scores.
   This run found one false blocked path out of seven checked so far.
2. **The rubric has no slot for it.** "Unaided recovery" scores whether a
   persona detected a *tool* error. There is no dimension for a persona
   inventing a defect that does not exist, which is the opposite failure and
   arguably worse, because it manufactures work.
3. **It cuts the other way too.** P2's mobile Inventory complaint was checked
   and is entirely real (O10). Confident negative claims are not uniformly
   unreliable, which is exactly why each needs checking rather than a blanket
   discount.

**RETRACTION, 2026-08-20.** This section originally cited P2's
external-dependency complaint as the verified-real counterweight, on the
grounds that `InventoryPanel.tsx` carries only four `onClick` handlers and none
is on a dependency entry. **That was wrong, and it was my error, not the
persona's.** `InventoryPanel.tsx` is the non-source-file drill-down and contains
no external-dependency content at all. The real surface is
`InventoryLensPanel.tsx`, which has implemented expand-and-navigate since
`fcdeab5` on 2026-08-18, before the mirror was generated. Browser verification
on 2026-08-20 confirms the feature works: clicking OpenAI adds exactly six
buttons, the six referencing components, each navigable. See O11.

**Scoring consequence.** P1's `advertised_paths` is not penalised for this
claim. It is recorded against P1's accuracy instead.

## O8. The tool asserts a contested port as settled fact. Trust incident, medium

Per `ANSWER-KEY.md`, the subject's own source disagrees with itself about USM
Core's port: `8767` is the Rust CLI's default flag, while a Swift client
hard-codes `8787` with a comment claiming it is the distinct new port, and the
prose architecture docs say 8787.

The published map states **`:8767`** on the `usm-core` node with no hedge and no
confidence marker, visible in `31-root-view.png`.

`8767` is the more defensible of the two, being the code default rather than
prose. The defect is not the value chosen, it is that a contested fact is
presented as settled. A tool whose central claim is trustworthiness should mark
this inferred, or surface the disagreement, in the same way it marks other
low-confidence output.

Recorded as a trust incident at medium severity. Neither persona raised it,
which is expected: the key marks it unscoreable for them precisely because the
subject's own source cannot settle it.

## O9. "Generated 18h ago" and a "Live" badge are shown simultaneously

Visible in the header in `31-root-view.png` and independently flagged by the
2026-08-19 P2 as a low-severity trust issue: "I read 'Live' as meaning 'this
reflects the current repo state,' but a snapshot generated 18 hours ago is not,
strictly, live."

The "Live" badge is driven by `live-config.json`, which points at an external
GitHub Pages origin for CI status overlay, so it means something different from
data freshness. Nothing in the interface explains that. Confirmed as a genuine
ambiguity, low severity, and cheap to fix with a word change.


## O10. The Inventory lens renders nothing below the 768px breakpoint. VERIFIED

The panel's container carries the Tailwind classes `hidden md:flex`, which is
`display: none` below 768px. At 390x844 the container's height is 0 and its
contents are absent from the page's visible text, while still present in the
DOM. Selecting the Inventory lens on a phone therefore produces no panel at all,
with no message explaining why.

The lens selector remains fully operable at that width, so the interface offers
a choice that silently does nothing. This is the surviving pillar of P2's
`advertised_paths` score of 0.

Confusingly, "Critical components" DOES appear in the page text at 390px. That
comes from the pinned summary banner, not from the lens panel, and it is exactly
the kind of partial signal that makes this defect easy to misdiagnose.

## O11. Retraction: the external-dependency drill-down works

Recorded as its own finding because a wrong verification is worth as much
attention as a wrong persona claim.

**What I asserted:** that external-dependency entries present an affordance they
lack, root-caused to `InventoryPanel.tsx` having no `onClick` on a dependency
entry.

**What is true:** the statement about `InventoryPanel.tsx` is accurate and
irrelevant. That file is the non-source-file drill-down. The external-dependency
surface is `InventoryLensPanel.tsx`, which expands a dependency on click
(line 134) and renders a navigable button per referencing component (line 159).
This landed in `fcdeab5`, 2026-08-18, an ancestor of HEAD and earlier than the
2026-08-19 mirror. The deployed bundle contains it: the literals "External
dependencies" and "No external services detected", the latter being the sibling
branch of the expand code, both appear in the shipped JavaScript.

**Direct verification, 2026-08-20.** Serving the mirror and driving it: clicking
OpenAI raises the button count from 164 to 170, exactly the six referencing
components.

**Why the persona hit a wall anyway.** Most likely an undismissed overlay. The
first-visit onboarding modal renders a full-viewport backdrop that intercepts
pointer events, and I reproduced that interception myself before dismissing it.
P2 drove the lens selector with `selectOption()`, a programmatic API that
bypasses pointer events entirely, so P2 could keep changing lenses through an
overlay that was silently swallowing every real click. That is a plausible
mechanism, not a proven one, and it is recorded as such.

**The lesson is about orchestrator verification, not about personas.** I checked
a plausible-looking file, found a fact that matched the complaint, and stopped.
Confirmation of a claim needs the same adversarial standard as refutation of one.

## O12. What the verification pass actually showed about persona reliability

Eleven persona claims have now been checked against source, evidence or a live
browser. The pattern is sharp and was not visible from any single claim.

**Interaction claims, 8 checked:**

| Claim | Persona | Outcome |
|---|---|---|
| Graph never renders | P1 | FALSE, contradicted by its own screenshot |
| Symbol search opens the parent, not the symbol | P1 | REAL, root-caused (O3) |
| "Classic frames" label does not match its effect | P1 | REAL, minor |
| Lens labels not clickable | P2 | ARTIFACT, native `<select>` |
| External dependency cards do not open | P2 | FALSE (O11) |
| Inventory lens dead at 390x844 | P2 | REAL, root-caused (O10) |
| Review mode produces no visible change | P3 | FALSE, it renders a banner and explanatory text |
| "More options" menu never appears | P3 | NOT A DEFECT, `display:none` at desktop, a mobile-only control |

Three false, two artifacts, three real.

**Data and consistency claims, 3 checked, all from P3:**

| Claim | Outcome |
|---|---|
| 254 versus 251 across two front doors | VERIFIED exactly |
| Changelog reports an id migration as real churn | VERIFIED exactly |
| `diff_summary` zeroed across 20 commits | CONFIRMED, with one correction |

Three for three.

**The conclusion, which should change how these runs are read:** agent personas
are reliable when reading data and unreliable when perceiving an interface. That
is coherent with what they are. They parse JSON accurately and they neither see a
rendered canvas the way a person does nor click the way a person does.

Consequences for the instrument: `advertised_paths` is the least trustworthy
dimension when personas are agents, and it is currently the lowest-scoring one,
so the score is being dragged down by exactly the dimension the harness measures
worst. Every claim feeding it must be reproduced before it scores. Data-side
findings need no such discount.

## O13. Search fetches the entire index, sequentially, on first open. Demo-blocking at private large-repository validation corpus scale. VERIFIED

Found while measuring the doc-indexing change, not by a persona, and invisible
on this subject.

`viewer/src/utils/search.ts::loadSearchShards` iterates every shard named in the
search manifest and `await`s each `fetch` **in series**. It is triggered from
`SearchOverlay.tsx:58` the first time the user opens search, guarded so it runs
once per session. Nothing fetches at page load, so this is not a page-load
regression.

Measured index size:

| Subject | Shards | Index size | Fetched on first search-open |
|---|---:|---:|---|
| UnaMentis | 9 | 7.67 MB (6.10 MB before doc indexing) | all of it, 9 serial requests |
| private large-repository validation corpus | 84 | **61.0 MB** | all of it, **84 serial requests** |

The private large-repository validation corpus figure is measured from the N2 pre-flight run and predates doc
indexing. Extrapolating this subject's +25.7% growth would put it near 77 MB,
but that extrapolation is weak: private large-repository validation corpus's documentation-to-code ratio differs
from UnaMentis's, so the real figure needs measuring rather than estimating.

**Why the comprehension review never caught it.** On UnaMentis the index is 6 MB
across 9 shards, so search feels fast. The 2026-08-19 P3 persona used search
heavily and rated it a strength. The defect only appears at a scale no reviewed
subject has yet had.

**Status.** Pre-existing, not introduced by the doc-indexing change, though that
change makes it roughly a quarter worse. It does not affect UnaMentis materially
and it would be a poor first impression on the demo programme's first public
subject.

**Not designed yet.** The obvious cheap step, fetching shards in parallel, does
not solve it: 61 MB is 61 MB. A real fix needs the index restructured so a query
touches a small part of it, for example a compact match index loaded first with
text fetched on demand, or term-based sharding. That is a design task, not a
patch, and it is recorded here rather than attempted inside a fix pass.

## O14. The flagship demo's "Live" overlay serves six-month-old data, republished daily so it looks current. VERIFIED

This began as P3's 254-versus-251 finding and turned out to be the shallowest
symptom of it.

**Measured directly against the live origins, 2026-08-20:**

| Surface | generated_at | analyzer_version | components |
|---|---|---|---|
| `solution-explorer.unamentis.org/architecture/manifest.json`, what the viewer renders | 2026-08-19T02:35:45Z | 1.2.0 | 254 |
| `unamentis.github.io/unamentis/architecture.json`, what the admin and Live overlay is built from | **2026-02-23T17:09:13Z** | **1.0.0** | 173 |

The stale file's HTTP `last-modified` is 2026-08-19T02:38:46Z. It is
**republished every run**, so every freshness signal available over the wire says
it is current while its contents are six months old and two analyzer versions
behind.

**Why nobody caught it.** The published number was 251, which is close enough to
254 to look like a rounding or scoping difference. It is not a count of anything:
`scripts/generate-admin-summary.py` re-walks the component tree itself rather
than trusting `stats.total_components`, and re-walking that old-schema file
yields 251, a number matching neither the file's own declared 173 nor the live
254. A plausible wrong number is far more dangerous than an obviously wrong one.

**Root cause is split across two repositories:**
- **Ours:** `generate-admin-summary.py` reimplements the count instead of using
  the analyzer's own contract-guaranteed total. Fixed here, with tests.
- **Not ours:** the `live-monitor.yml` running in `UnaMentis/unamentis` has
  drifted from both this repo's workflow and the shipped template, gaining a
  branch that prefers a committed root-level `architecture.json` over running a
  fresh scan. That committed file was last updated 2026-02-23. **This cannot be
  fixed from this repository** and is reported rather than patched.

**This is exactly the failure the demo programme exists to prevent**, sitting on
the flagship demo: a maintained map that presents stale output as live. It also
fully explains O9. The 2026-08-19 P2 persona flagged "Generated 18h ago" beside a
"Live" badge as a wording ambiguity worth a precise definition. The reality is
that the two surfaces were describing different datasets six months apart.

**Consequence of the fix, and it is a feature.** With the count taken from the
file's own stats, the admin summary will now report 173 against the viewer's 254,
and the new mismatch warning fires. The failure becomes loud instead of
plausible. Given the alternative is a number that silently looks right, loud is
correct.

**Owner action required**, outside this repository: repoint or remove the
committed `architecture.json` in `UnaMentis/unamentis` so the Live overlay is
built from a fresh scan.


## O13 CORRECTED, 2026-08-20. The search index was not demo-blocking, and I said it was

O13 above is left standing as written so the error is visible. It is wrong in
its severity and in its proposed remedy, and the correction is more useful than
the finding.

**What I got wrong.** I reported that the first visitor to open search on VS
Code would wait on 61 MB across 84 requests. I measured a directory listing and
never checked what the origin actually transmits.

**Measured against the live origin.** Cloudflare already serves these files
brotli-compressed. One shard: 685,776 bytes on disk, **93,718 bytes over the
wire**, 7.3x. The whole private large-repository validation corpus index compresses to **2.9 MB**, not 61 MB.

**Measured against the real product.** Running private large-repository validation corpus's dataset through the
actual viewer: search returns usable results in **451 ms**, with only 36 of 85
shards loaded. Matching runs against the already-loaded architecture and the
shards *enrich* an index that is usable from the start. Nobody waits for the
full load.

**The design I was about to propose was not viable either.** A two-tier split
with a small match tier fails because matching reads `name`, `path`, `kind` and
`text`, so `text` cannot be deferred. The only droppable field is `component`,
7.17% of bytes. The best-case match tier is 40.5 MB, two-thirds of the index.

**What was actually wrong, and is now fixed.** Two real but small things: 85
sequential round trips, and a silent partial-results window where search looked
complete while still filling.

Both fixed. Bounded-concurrency fetching at 6 workers, assembled in shard
manifest order rather than arrival order so ranking stays deterministic, plus an
"Indexing…" indicator that becomes "Index incomplete" if shard loading fails
outright, so a failure never reads as a complete index.

Verified in a real browser on the private large-repository validation corpus dataset: max concurrency 6, all 84
shards in **276 ms** against 1,171 ms sequential, indicator clearing correctly.

**Why this belongs in the record.** It is the second time in this run that I
confirmed something without holding it to the standard I hold refutations to.
The first was O11, the dependency cards. Both followed the same shape: a
plausible fact, a partial check, a confident conclusion. Refutation felt like it
needed justifying and confirmation felt pre-justified. That asymmetry is a bias
worth designing against, and it is now rule 7 in the charter.

**The wider lesson, which the owner turned into policy.** One subject could not
distinguish "expensive at scale" from "expensive-looking on paper". Work whose
value is hard to establish now waits for a wider sampling of projects. See the
Wave 1 retrospective register in `docs/publication/HANDOFF-DEMO-PROGRAM.md`.
