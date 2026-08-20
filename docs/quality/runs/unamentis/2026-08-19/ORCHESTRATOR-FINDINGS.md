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
3. **It cuts the other way too.** P2's apparently similar complaint, that
   external dependency cards do not open, was checked and is entirely real:
   `InventoryPanel.tsx` carries only four `onClick` handlers and none is on a
   dependency entry. Confident negative claims are not uniformly unreliable,
   which is exactly why each needs checking rather than a blanket discount.

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
