# REVIEW: unamentis-ios front-door run, 2026-09-01

Charter `comprehension-review/v1`. Subject: `unamentis-ios` at `a5717bf`.
Run date 2026-09-01, sittings 21:05Z to 21:30Z, three Opus personas run
concurrently on the Playwright MCP transport (`@playwright/mcp` 0.0.80,
`--isolated --headless`, 1440x900). Served interface:
`http://127.0.0.1:5173/?mode=overview`, the canonical bundle from
`wt/frontdoor-production` at `06a3fc3` over the 2026-08-30 full enrichment run
(manifest `c8d92a18…`). Front-door content hash `daf37a22…` at launch and at
close: nothing moved under the personas.

This run replaces the morning run of the same date, which measured a March
2026 projection of the `unamentis` monorepo with Sonnet personas. That run's
findings were correct about what it saw; what it saw was stale. Its two
reports, "Front Door Comprehension Review" and "Data Side, Glass Side", are
superseded by this record and the report that accompanies it.

The combined report is `REPORT.html` in this directory, also published at
https://claude.ai/code/artifact/6f3ea0c6-1541-4e30-8178-6043fc910cd1.

Raw persona material, 82 screenshots, journals, findings, transcripts and the
harness's own console captures, is at `/private/tmp/comprehension-20260901-rerun/`
and is not committed.

## The result

```
unamentis-ios (comprehension-review/v1)

Persona                                    Score       Battery         Trust   Blocked
P1 senior engineer, unfamiliar language   16/24    3c/2p/0w/0u   12 (2 high)      7
P2 non-coding executive                   14/24    1c/4p/0w/0u    8 (1 high)      7
P3 staff engineer, AI power user          16/24    5c/0p/0w/0u    8 (1 high)      6
```

Reported as the set, never the average. All three personas graded B minus.

**Not comparable to any earlier number.** Every previous run measured the
four-repository monorepo (254 to 256 components, 1.1M to 3.8M lines). This
one measures the iOS client alone (168 components, 200K lines) on a
projection from the rebuilt engine, with a different persona model. The
profile difference is recorded in `PROFILE.json`. Comparison is in kind
only, below.

## What the personas got

**Orientation is solved, again, and faster.** Fifteen seconds (P2), one
minute (P1), two minutes (P3) to a correct one-paragraph description. Every
fact in that paragraph that any persona checked held. All three named the
protocol seam and its 33 dependents as the organising idea, and the key
agrees.

**All three finished early.** Six, nineteen and seventy-eight minutes of a
ninety-minute box. P1 stopped because "I had run out of questions the tool
could answer"; the remaining questions, ports and backend internals, it judged
unreachable at any budget.

**The measured layer is consistent.** P3 chased the component count through
seven routes and the STT component's metrics through four, and everything
agreed to the digit. The morning's headline defect, two totals for the same
repository on one screen, did not recur. That is the regenerate-on-current-
pipeline track from the morning's plan, delivered.

**The narrated layer is where trust broke, in every sitting.** Capability
lens, Rules lens, Security lens, tour counts, the fallback narrative, the
external-reliance list. P3 named the pattern: the JSON labels inferred and
interpreted content correctly, and the UI strips the labels off, so "an agent
consuming ai.json is better protected than a human clicking the SPA".

## The finding the owner asked for: deployment posture

The app is standalone-first. The backend is optional, exists for
organizational use, and is never required for normal use; cloud inference,
when the on-device model is not enough, goes straight from the device to the
provider with the user's key. The owner stated this during the run, and the
source says it in one sentence at `CLAUDE.md:19`.

The interface does not say it anywhere. `orientation.json` contains neither
"standalone" nor "server". The enrichment describes discovery as "finding the
backend server" and the tour says a manager "tracks the self-hosted server",
with no statement of whether that server is required. The consequence in the
sittings:

- P2 reached the right conclusion, "we operate almost no infrastructure", and
  then withdrew confidence from it: "I would not stand up in front of a board
  claiming 'no infrastructure of our own' until someone answers this."
- P1 found the backend at minute nineteen by opening `CurriculumService` on a
  hunch, and wrote that had it stopped at minute fifteen it "would have walked
  into a design review confidently describing a client that talks only to
  third-party AI vendors."
- P1 also spent part of its sitting looking for a WebSocket to the backend.
  There is none; the link is plain HTTP REST on 8766.

**Attribution: the tool's side, on both halves.** The repository is
unambiguous. The generator has no notion of deployment posture, what must
exist for the system to run and what is optional, and so cannot emit it; the
interface has no surface that would show it if it did. The morning's monorepo
run made the mirror-image error for the same reason, presenting the backend
as something the clients "fail without", because criticality is inferred from
fan-in rather than from what the subject says is required. Full evidence in
`ORCHESTRATOR-FINDINGS.md` O5.

## Independent verification

Convention: **VERIFIED** means a root cause was found, **CONFIRMED** means
reproduced or corroborated, **REFUTED** means the claim did not survive.

| # | Finding | Status | Root cause or evidence |
|---|---|---|---|
| O1 | Capability lens is Swift string-interpolation fragments | VERIFIED | `derive/capabilities.py:200-212` turns every `queue_name` signal into an event capability; the Swift extractor fires on a `topic:` argument label |
| O2 | Security lens cannot see a Keychain | VERIFIED, structural | `human_views.py:310-345` derives mechanisms only from edge auth fields and credentials only from env-var names; this projection has no edge with a protocol |
| O3 | Trust ledger calls 82 enrichment abstentions "failed or absent analyzer units" | VERIFIED | all 82 gaps are `enrich.verify-identity`; P2 repeated the label in its brief |
| O4 | "100% source mapped" is parsed over parseable, undisclosed | VERIFIED | 757 parsed, 34 binary, 19 excluded, 810 total; the 53 removed rows are not shown |
| O5 | Deployment posture never stated | VERIFIED, both sides | above |
| O6 | SBOM cites a stray agent worktree; tools version listed eight times; reads the vestigial manifest | VERIFIED | `sbom/collector.py` prunes neither `.claude` nor untracked nested worktrees; eight `Package.swift` found; the build uses `project.yml` (6 packages) |
| O7 | Tour counts and fallback claim not supported by source | VERIFIED | 8 STT, 6 TTS, 7 LLM actors against "six", "seven", "seventeen"; `FallbackLLMService` is never constructed by the app |
| O8 | 751 vs 757 files are the six CI workflows | VERIFIED | parsed for coverage, owned by no component |
| O9 | Subject's committed `architecture/` read as source | VERIFIED, attribution corrected | git `2112f12` in the subject; 73 of 778 rules and 34 of 176 ai_surface entries come from it |
| O10 | Machine front door not linked from the UI; `llms.txt` incomplete | VERIFIED | P3 found it through a `python -m http.server` directory listing |
| O11 | No edge carries port, protocol or auth | VERIFIED | 458 edges: uses, navigation, import, modal, tab |
| O12 | Rules lens 778 inferred switch and formula sites; Auth concern is keyword noise | CONFIRMED | 54 rules with multi-line code as inputs; `AudioEngineConfig.swift:274` is an errorDescription switch |
| O13 | Escape does not close the trust drawer; drawer blocks header; onboarding modal likewise; guided-paths chip dead during a tour | VERIFIED | no key handler in `TrustDrawer`; `TourPlayer.tsx:178-182` |
| O14 | Flow lens NaN rendering | CONFIRMED from capture, not reproduced | 118 NaN attribute errors in P2's harness console log at 158 s; five orchestrator routes rendered 78 clean paths |
| O15 | Phone Support panel | CONFIRMED with correction | heading in viewport; content in a 199 px scroller; P2 withdrew its own first conclusion |
| O16 | Structure lens at System, Domain and Component levels renders one node and no edges without a drill | CONFIRMED | probe6: 1 node, 0 edges at all three levels |
| O17 | `core/audio` help_text says "no evidence shows audio capture" while its description and the tour say it captures the mic | VERIFIED | same component, two enrichment fields |
| O18 | Component-panel GitHub link resolves to a directory; symbol-panel link resolves to a line range | CONFIRMED | both P1 and P3 were right about the surface each looked at |

### Claims checked, claims excluded

| Persona | Checked | Verified or confirmed | Refuted | Excluded (rule 8 or by design) | Corrected |
|---|---|---|---|---|---|
| P1 | 19 | 14 | 1 (no close control on the drawer) | 3 (off-screen click; 404s; guided chip, withdrawn by P1) | 1 (contamination attribution) |
| P2 | 15 | 11 | 1 (82 gaps equals 82 findings) | 2 (phone Support, first conclusion; 404s) | 1 (phone Support, measurement) |
| P3 | 14 | 9 | 1 (ai_surface excess, not a defect) | 3 (root llms.txt; 404s; clipboard) | 1 (contamination attribution) |

Not established either way: "0 transitive dependencies" (the collector did
not read the committed `Package.resolved`).

### Added by the orchestrator, not raised by any persona

- O3, the ledger label. All three personas read "82 gaps"; P2 alone carried
  the caption into a deliverable, and none noticed the caption is false.
- O7's fallback half. P1 built its leading bug hypothesis on it; P2 put it in
  its board brief. Neither could have known from inside the tool.
- O17, the audio narrative contradicting itself. P1 raised the tour-versus-
  insight disagreement; the second field on the same component is the cause.

## Comparison in kind with the morning run

| Morning finding (March monorepo data) | This build (August iOS data) |
|---|---|
| Two component totals, two relationship totals on one screen | Gone. 168 across seven routes, 458 across every route. Regeneration fixed the class |
| Trust ledger prints 0 for absent sidecars | Did not fire; every sidecar exists. The `?? 0` fallbacks are still in `utils/orientation.ts:155-160` and will fire on the next projection that lacks one |
| "Answer assembled from mapped evidence" over a redirect | Banner still static at `SystemOverview.tsx:127`; with four tours present the flow route now has content behind it |
| Enrichment undercounts endpoints by 46% | No endpoints in this subject; the same class appears as tour counts (O7) |
| Scripts directory presented as a Ruby service with a port | Gone with the subject; the analogous aggregate-naming defect here is the committed `architecture/` directory becoming three components (O9) |
| Phone: question route lands behind a component sheet | Not reproduced; the phone problem here is the 199 px scroller (O15) and the onboarding modal |
| Four endpoints 404 on load | Two, by design of this bundle |
| Staleness not flagged | "Generated 1d ago" now renders; P3 called it good |
| Search is exact-substring, undisclosed | Unchanged; P1 hit it again |

The class that dominated the morning, absence rendered as a confident number,
is absent from this build because the data is complete. The class that
dominates this run, inferred and interpreted content rendered with the
authority of measured content, was present in the morning too (the "over
140 endpoints" prose) and was under-weighted there because the count
contradictions were louder.

## Instrument retro

**R1. Concurrent Opus sittings on the Playwright transport worked without
incident.** 25 minutes wall clock for all three, 82 screenshots, no browser
loss. The harness's own console capture (`artifacts/console-*.log`) turned
out to be the decisive evidence for O14, where the persona's claim could not
be reproduced. Keep the captures; they are the only record of intermittent
faults.

**R2. Persona reliability split holds.** Data claims: every one verified
exactly, including P3's set difference and P2's SBOM path. Interface
perception: two of nine claims refuted, one corrected, one modality artifact.
Same pattern as 2026-08-19. Rule 7 earned its place again.

**R3. Opus personas stop early and say why.** Six to seventy-eight minutes
against a ninety-minute box, each with a stated reason. The box is now an
upper bound rather than a measurement, and "why the persona stopped" is
better signal than elapsed time. Candidate for v2: record the stop reason as
a field.

**R4. The subject changed under the instrument.** The answer key from
2026-08-19 covers the monorepo and required `/ws/audio` on 8766 as a
must-appear fact. Read from the iOS repository alone, that endpoint does not
exist. A new key was built (`ANSWER-KEY-unamentis-ios.md`, 947 lines) by an
agent with no access to this repository or to any projection. Keys are
per-subject and this one is reusable; the charter's "built once per subject"
rule was followed, but the run record should say which key it used.

**R5. Owner statements during a run.** Two arrived mid-run (standalone-first;
direct-to-provider). Both were checked against the source before use and both
held. Recorded as such rather than as ground truth on their own, which is the
right discipline and should be written into the charter.

**R6. The serving harness's directory listing is a confound.** P3's route to
the machine front door went through `/architecture/`, a `python -m http.server`
default. The production origin would not offer it. The finding (nothing links
`llms.txt`) stands; the eight minutes P3 spent do not transfer.

**R7. Which questions failed to discriminate.** Orientation: 4, 4, 4. Trust:
1, 1, 1. Neither separates anything on this subject. Model accuracy and
advertised paths carried the signal.

No charter version bump. Nothing here changes how a score is computed.

## Disposition

The interface teaches this system and does so in minutes, to three different
readers, including one who cannot read Swift. That was the goal of the front
door and it is met on current data.

It is not ready to put in front of a buyer with the Capability and Rules
lenses switched on, the Security lens reporting zero on an app that uses the
Keychain, the trust ledger mislabelling its own caveat, or the tours stating
counts and a fallback the source does not support. Each of those puts a false
sentence in a careful reader's mouth, and in this run two personas carried one
into a deliverable.

And it needs one new fact it has never had: what this system requires in
order to run. Nothing in the projection or the interface answers that, and
for this subject it is the single most important commercial fact there is.

Ordered repairs, with the side that owns each, are in the accompanying
report.
