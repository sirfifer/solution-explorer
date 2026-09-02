# Orchestrator findings, unamentis-ios front-door run, 2026-09-01

Findings the orchestrator established independently during verification, with
root causes where one was found. Separate from persona findings. Convention:
**VERIFIED** means a root cause was found; **CONFIRMED** means reproduced or
corroborated only; **REFUTED** means the claim did not survive checking.

Subject: `unamentis-ios` at `a5717bf`, projection generated 2026-08-31T05:50Z,
enriched 2026-08-31 (ai_enhance v2), analyzer 1.2.0 on the
`deterministic-gate-hardening` checkout. Interface: `wt/frontdoor-production`
at `06a3fc3`, production bundle built 2026-09-01 13:43. Served at
`http://127.0.0.1:5173/?mode=overview`, snapshot hash
`daf37a22…` taken at launch and again at close (unchanged).

Ground truth: `ANSWER-KEY-unamentis-ios.md`, built by an agent that read only
the subject's source and docs, with no access to this repository or to any
projection output. Owner statements received during the run are recorded as
such and were checked against the source before use.

---

## O1. The Capability lens is built from Swift string-interpolation fragments. VERIFIED

`manifest.capabilities` holds three entries: `topic`, `t-\(index)` and
`topic-\(index)`, all `kind: event`, all `confidence: inferred`. Sources:
`UnaMentis/Core/Todo/TodoItemType.swift:12` (an enum case) and
`UnaMentisTests/Unit/Telemetry/TelemetryEngineExtendedTests.swift:112,144`
(`telemetry.recordEvent(.topicStarted(topic: "t-\(index)"))`).

**Root cause.** `analyzer/derive/capabilities.py:200-212` turns every
`queue_name` signal into an event capability, unconditionally. The Swift signal
extractor emits a `queue_name` signal for the `topic:` argument label, so a
telemetry test helper and a todo enum become the system's complete capability
inventory. The viewer (`CapabilityPanel.tsx:98`) then renders
"3 capabilities · 0 proven by tests" and marks each "untested", without the
`inferred` label the JSON carries.

Downstream: the same three entries are the Support lens's "Entry points (3)"
and feed the bottom of its ranked-attention list. Raised by P1, P2 and P3
independently; P2 rated it the single most damaging thing in the sitting.

## O2. The Security lens cannot see a Keychain. VERIFIED, structural

`security.json` reports `mechanisms: 0` and `credential_configuration: 0`.
The source uses the Keychain for all ten API keys
(`UnaMentis/Core/Config/APIKeyManager.swift:32-42`, service
`com.unamentis.apikeys`), and the tool's own tour says so.

**Root cause.** `analyzer/project/human_views.py:310-345`
(`build_security_view`): mechanisms come only from relationship
`authentication` and `middleware` fields; credentials come only from
component `docs.env_vars` names. This projection has 458 edges, none carrying
a protocol, port or authentication field (O11), and an iOS app declares no env
vars. A Keychain-based client therefore scores zero by construction, and the
lens prints the zero as "CONFIRMED MECHANISMS (0)". The `not_observable` list
beneath it is honest about runtime facts but does not say that on-device
credential storage is outside the detector's model.

## O3. The Trust ledger mislabels 82 enrichment abstentions as analyzer failures. VERIFIED

`TrustLedger.tsx:23` renders `producer_gaps` with the caption "failed or
absent analyzer units". Every one of the 82 entries in `manifest.gaps` has
`producer: enrich.verify-identity` and `status: unresolved`: 37 framework, 33
name, 11 type, 1 port. They are the enrichment engine declining to confirm an
identity claim from the facts it was given. No analyzer unit failed; the
coverage ledger is complete (757 parsed, 0 failed).

P2 read the caption literally and wrote "82 analyzer passes failed" into its
board brief. That is a false statement induced by the label, and the persona
did not catch it. Counted as a trust incident against the tool.

## O4. "100% source mapped" is parsed over parseable, undisclosed. VERIFIED

`coverage.summary`: parsed 757, binary 34, excluded 19, total 810.
`analyzer/project/coverage.py:format_source_percent` divides parsed by parsed
plus failed, which yields 100% whenever nothing failed. The definition is
defensible: binaries and gitignored files are not source. The defect is that
the panel titled "What this view knows and what it does not" does not show the
53 rows it removed from the denominator, and the compact chip renders the
reassuring figure in bold with the caveat in small grey. P3 spent five minutes
proving the number was not simply wrong.

## O5. The map never states the app's deployment posture. VERIFIED, both sides checked

The owner stated during the run that the app is standalone-first: the backend
is optional, exists for organizational use (curriculum publishing, user
tracking, modules, hosted inference) and is never required for normal use;
cloud inference, when the on-device model is not enough, goes straight from
the device to the provider with the user's key and no proxy.

**The source says exactly this.** `CLAUDE.md:19`: "This is a standalone mobile
app. It communicates with the UnaMentis server via HTTP REST APIs (port 8766)
but has zero source-level dependencies on server code." The self-hosted path
is gated behind `selfHostedEnabled` (`SessionView.swift:1490`). Every provider
call goes direct from the device over HTTPS or WSS with the Keychain key
(`OpenAILLMService.swift:21`, `DeepgramSTTService.swift:17`, and the rest in
the key's P1.2). Nothing traverses the backend.

**The projection carries the sentence, buried.** The word "standalone" occurs
8 times in `manifest.json`, all inside doc excerpts copied into component
`docs` fields. `orientation.json`, the document that drives the front door,
contains neither "standalone" nor "server". The enrichment describes
`core/discovery` as a "Multi-tier network discovery orchestrator for finding
the backend server" and the tour says `ServerConfigManager` "tracks the
self-hosted server", with no statement of whether that server is required.

**Consequence.** P2 arrived at the right conclusion ("we operate almost no
infrastructure") and then withdrew confidence from it because a server it
could not find in the map was named in a tour: "I would not stand up in front
of a board claiming 'no infrastructure of our own' until someone answers
this." P1 spent part of its sitting looking for a WebSocket to the backend
that does not exist. The single most important commercial fact about this
system, that it runs without anyone's server, is not a first-class fact in
the projection and is not presented anywhere in the interface.

**Attribution.** The repository is unambiguous. The misrepresentation is on
the tool's side, in two places: the generator has no notion of deployment
posture (what must exist for the system to run, and what is optional), and
the interface has no surface for it. This morning's monorepo run made the
opposite error for the same reason, presenting the backend as a component the
clients "fail without", because criticality is inferred from fan-in rather
than from the subject's own statement of what is required.

## O6. SBOM evidence points into a stray agent worktree. VERIFIED

All seven `supply_chain.dependencies` cite
`.claude/worktrees/agent-a47f3b12323d6bde3/Package.swift`, and the CycloneDX
metadata lists "swift-tools 6.0" eight times.

**Root cause.** `analyzer/sbom/collector.py:337-360` prunes a fixed set of
directories and anything `.gitignore` matches. The subject checkout carries
seven untracked, un-ignored nested worktrees under `.claude/worktrees/`, each
with its own `Package.swift`. The coverage enumerator skips `.claude` as a
directory (`coverage.rows[0]`), the SBOM walk does not, so eight manifests are
found, eight tool-version properties are emitted, and `_dedupe_and_rank`
(`:257-262`) keeps the lexicographically smallest evidence path, which is the
one starting with a dot. The dependency set happens to be identical to the
root manifest, so the content is right and the citation is wrong. A citation
into a path the tool's own ledger marks as skipped is a trust defect in a
product whose pitch is evidence.

Related and deeper, from the key: the shipped app is built by XcodeGen from
`project.yml`, which declares six packages, not the seven in `Package.swift`
(llama.cpp removed in favour of a prebuilt xcframework; SwiftSoup and
FluidAudio present; SwiftMath and Komondor absent). The SBOM reads the
vestigial manifest. "0 transitive" is a non-measurement: the collector lists
`Package.resolved` as a candidate but the committed one under
`UnaMentis.xcodeproj/…/swiftpm/` was not read.

## O7. Tour narration asserts counts the source does not support. VERIFIED

The `provider-seam` tour is titled "How seventeen providers coexist" with
steps "Six STT implementations" and "Seven TTS implementations", and states
that `FallbackLLMService` "chains providers so a failed call degrades to the
next tier instead of failing the turn".

Source: eight actors conform to `STTService` (seven in the build), six to
`TTSService`, seven to `LLMService` of which two are `Mock` and `Fallback`.
No decomposition yields seventeen. `FallbackLLMService` is referenced outside
its own file only by two test files; the app never constructs it
(`grep -rn 'FallbackLLMService(' UnaMentis` returns nothing). The runtime
LLM chain is hand-rolled at session start in `SessionView.swift:1651-1800`
and does not fail over mid-turn.

The tour carries `provenance.derived_from_commit: a5717bf` and per-step
`evidence: {file, line}`. The evidence pointers are real; the numbers and the
fallback claim in the prose were not derived from them. Both P2 and P1
carried the fallback claim into their answers.

## O8. Six CI workflow files are counted for coverage and owned by nothing. VERIFIED

`stats.total_files` 751; `coverage.parsed` 757. Set difference of
`coverage.rows[disposition=parsed]` against every `ref_kind: file` search
entry: exactly the six `.github/workflows/*.yml` files. Parsed, credited to
coverage, assigned to no component, absent from search and from every UI
surface. P3's finding, reproduced exactly.

## O9. The subject commits an old copy of this tool's output, and the analyzer read it as source. VERIFIED, attribution corrected

`architecture`, `architecture/data` (189 files) and `architecture/search` are
three of the 168 components. The subject repository commits a July 2026
`architecture/` snapshot (`git log`: `2112f12`, "Add AI-enriched architecture
baseline (solution-explorer v2)"), produced by its own CI
(`.github/workflows/architecture.yml` runs `sirfifer/solution-explorer@main`).

Effects: 73 of 778 rules and 34 of 176 `ai_surface` entries are derived from
those JSON files, including `ANTHROPIC_API_KEY` reported at confidence
`certain` from `architecture/data/detail-unamentistests--unit.json:1`; the
Auth concern's first member is `architecture/data`; the first rule in the
array has Swift enum cases with embedded newlines as its "outputs".

P3 attributed this to the analyzer scanning its own output directory. It did
not; the directory is the subject's. The fix is the same either way: a
projection directory inside a subject should be recognised and excluded, and
a `policy-rule` signal should not fire on JSON.

## O10. The machine front door is not linked from the interface. VERIFIED

`llms.txt` and `ai.json` exist only under `/architecture/`. Nothing in either
shell links to them. P3 found them through the `/architecture/` directory
listing, which is a `python -m http.server` default and would not exist on
the production origin. `llms.txt` also omits `orientation.json`,
`support.json` and `security.json`, all of which the app itself fetches, and
`orientation.json` at 11 KB is the best single answer to "what is this
system" in the dataset.

## O11. No edge in this projection carries a port, protocol or authentication. VERIFIED

All 458 relationships are `uses` (381), `navigation` (34), `import` (26),
`modal` (12) or `tab` (5). Zero carry `port`, `protocol` or `authentication`.
The client-to-backend transport (HTTP REST, 8766, no TLS, no auth token) and
the direct-to-provider transports (HTTPS and WSS to nine services) are
answerable only from enrichment prose and symbol search. P1's Q2 depended on
finding `SelfHostedSTTService.buildWebSocketURL`, a file excluded from the
build, and concluded the backend link is a WebSocket. It is not.

This is also why O2's mechanism count is zero and why the Security lens shows
458 boundaries all marked "unknown · not observable".

## O12. The Rules lens presents 778 inferred switch and formula sites as rules. CONFIRMED

`manifest.rules`: 560 `switch` anchors, 217 `formula`, 1 `case_when`, all
`confidence: inferred`, 54 with multi-line code fragments as inputs or
outputs, 73 from the committed architecture directory (O9). The Auth concern
(`basis: "auth library imports"`) is 15 members whose evidence is
`policy-rule` signals in files such as `AudioEngineConfig.swift:274`, an
error-description switch. P1's characterisation, "778 rules that are mangled
JSON blobs" and "Auth concern is keyword false positives", holds on the sample
checked.

## O13. Escape does not close the trust drawer, and the drawer then blocks the header. VERIFIED

`TrustLedger.tsx` `TrustDrawer` registers no key handler. Reproduced in
`orchestrator/probe5.mjs`: drawer open after Escape, and a subsequent click
on the "4 guided paths" chip times out because the drawer's backdrop
intercepts it. The first-visit onboarding modal in the Classic workbench
("Welcome to Architecture Visualizer") also ignores Escape and blocks the
header until Skip is pressed. The guided-paths chip does nothing while a tour
is active (`TourPlayer.tsx:178-182`: an active tour suppresses the list).

## O14. Flow lens NaN rendering. CONFIRMED from capture, not reproduced

P2's harness console log (`P2/artifacts/console-2026-09-01T21-05-53-748Z.log`)
records 118 errors of the form `<path> attribute d: Expected number,
"MNaN,NaN…"` and `<rect> attribute x: Expected length, "NaN"` at 158 seconds
into the sitting, when P2 switched to Flow. The orchestrator tried five
routes (deep link; lens switch from Data; switch with the trust drawer open;
a phone-to-desktop resize; the question route) and observed zero NaN
attributes and 78 clean paths each time. Treated as real and intermittent,
most plausibly a layout pass that runs before the canvas has a measured
size. P2's screenshot of the same moment shows the graph fully drawn behind
the drawer, so the errors did not leave the diagram blank.

## O15. Phone: the Support answer is in view, inside a 199 px window. CONFIRMED with correction

At 390x844, `?mode=workbench&lens=support`: the "Ranked attention" heading
sits at y=585, inside the viewport, but the panel scrolls within a container
199 px tall (scrollHeight 1,774) beneath the diagram; "External reliance" is
1,663 px down inside it. P2's "1,700 pixels below the fold" measured the inner
scroller, and its first conclusion, that the phone drops the panel, was
wrong; its corrected conclusion, that the panel is not usable in a hallway,
stands. The first-visit onboarding modal also appears on the phone.

---

## Persona claims checked, and what happened to them

| Claim | Persona | Outcome |
|---|---|---|
| Capability lens is parser debris | P1, P2, P3 | VERIFIED (O1) |
| Security lens 0 mechanisms contradicts Keychain use | P2 | VERIFIED structural (O2) |
| Backend server missing from a "100% mapped" map | P2 | VERIFIED as a posture gap (O5); the server is a separate repository |
| SBOM cites an agent worktree | P2 | VERIFIED (O6) |
| 82 gaps equals 82 findings, one number wired twice | P2 | REFUTED, coincidence |
| 0 transitive dependencies is suspicious | P2 | Not established either way; non-measurement (O6) |
| Swift tools version listed eight times | P2 | VERIFIED, one per manifest found (O6) |
| Flow lens threw ~118 NaN errors | P2 | CONFIRMED from console capture, not reproduced (O14) |
| Phone buries Support 1,700 px down | P2 | CONFIRMED with correction; first conclusion withdrawn by the persona itself (O15) |
| Escape leaves a modal open that eats clicks | P2 | VERIFIED (O13) |
| Guided-paths button dead during a tour | P2 | VERIFIED in code (O13) |
| "100% source mapped" hides 53 rows | P3 | VERIFIED (O4) |
| 751 vs 757 files are the six CI workflows | P3 | VERIFIED exactly (O8) |
| Tour counts wrong | P3 | VERIFIED against source (O7) |
| Analyzer scanned its own output | P3 | VERIFIED as contamination, attribution corrected (O9) |
| STT shard larger than its source | P3 | VERIFIED sizes; code_preview is 26,648 of 129,710 chars |
| ai_surface 176 vs 168 components | P3 | RESOLVED, not a defect: a signal list, not a per-component table |
| Rules lens is 778 mangled entries; Auth concern is keyword noise | P1 | CONFIRMED on sample (O12) |
| Backend link is a WebSocket | P1 | REFUTED by the key; REST only (O11) |
| Root /llms.txt 404s | P3 | EXCLUDED, bundle strips root copies by design |
| Load-time 404s | all | EXCLUDED, by design for this bundle |
| Clipboard read denied | P3 | EXCLUDED, harness |

Counts are finalised in `REVIEW.md` once P1's card is scored.

## O16 to O18, added after P1's card was scored

**O16. Structure lens renders one node and no edges at System, Domain and
Component levels until the reader drills. CONFIRMED** (`orchestrator/probe6.mjs`:
1 node, 0 edges at all three `semantic_level` values with no `drill`
parameter). P1's "the level buttons appear to do nothing" holds as seen.

**O17. `core/audio` contradicts itself across two enrichment fields. VERIFIED.**
`description`: "Audio pipeline: capture, VAD barge-in, TTS caching, playback
orchestration". `help_text`: "no evidence shows audio capture or VAD mechanics
specifically". The tour's step 1 says AudioEngine captures the mic. Same
component, same enrichment pass.

**O18. GitHub links resolve differently by surface. CONFIRMED.** The component
panel links to a directory (`blob/main/UnaMentis/Services/LLM`); the symbol
panel links to a line range. P1 and P3 each described the surface they used.

**Data lens writers, from P1. VERIFIED as O9.** `entity_access` records
`architecture` writing `TranscriptEntry` at confidence `certain`, evidence
`architecture/manifest.json:1`, the subject's committed snapshot.

Final counts are in `REVIEW.md`.
