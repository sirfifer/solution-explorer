# RECHECK: the live front door against the 2026-09-01 review

Orchestrator re-check, no persona sittings. Performed 2026-09-01 23:30Z to
23:50Z against `http://127.0.0.1:5173/?mode=overview`, which now serves
`wt/comprehension-review-remediation` (uncommitted: 31 files modified, 4
new) from `.testboard/serve/unamentis-ios`. The projection was regenerated
at 2026-09-01T23:14Z on the same subject commit `a5717bf` with the same
2026-08-31 enrichment; no model spend. Bundle `index-B17SXsyU.js`. Live data
snapshotted to `/private/tmp/comprehension-20260901-rerun/frontdoor-live-recheck/`,
browser probes in `orchestrator2/`. The 154 analyzer tests in the touched
test files pass (`pytest` via the main checkout's virtualenv). Viewer tests
were not run by the orchestrator.

## Status of every finding in REVIEW.md and REPORT.html

| # | Finding | Status now | Evidence |
|---|---|---|---|
| O1 | Capability lens is string-interpolation fragments | **Fixed** | `capabilities: []`; route `capabilities` is `available: false`; the lens is gone from the switcher; `?lens=capability` falls back to Structure; the `queue_name` rule is guarded |
| O2 | Security lens cannot see a Keychain | **Fixed** | `mechanisms: 2` (iOS Keychain from `APIKeyManager.swift`, iOS file protection), `credential_configuration: 1`; 470 boundaries now include 9 https and 3 wss provider references |
| O3 | Ledger caption "failed or absent analyzer units" | **Fixed** | "Producer claims 80 · 80 unresolved"; chip reads "80 unresolved claims" |
| O4 | "100% source mapped" undisclosed denominator | **Fixed** | "559/810 files mapped"; drawer reads "34 binary · 217 excluded · 0 parse gaps" |
| O5 | Deployment posture never stated | **Fixed** | `orientation.deployment_posture`, four evidence-tiered items (standalone, server optional, on-device, direct-to-provider) with source pointers, rendered on the Overview beneath the description and labelled repository claim versus observed source reference |
| O6 | SBOM cites an agent worktree; tools version eight times | **Fixed, one part open** | evidence now `Package.swift`; one tools property; `.claude/worktrees` pruned. Still reads `Package.swift` (7) where `project.yml` (6) builds the app, and `Package.resolved` is still unread so transitive stays 0 |
| O7 | Tour counts and fallback claim | **Fixed by a tracked overlay** | `demos/review-corrections/unamentis-ios.json` applied by `scripts/apply-review-corrections.py`: seven exact-value edits bound to the commit, recorded in `manifest.review_corrections`, refused if stale. "Seventeen", "six", "seven" removed; the fallback sentence now says this static review found no evidence the app constructs it |
| O8 | Six CI files owned by nothing | **Fixed** | the six `.github/workflows/*.yml` are owned by `root`; files 559 in stats, search and coverage |
| O9 | Subject's committed snapshot read as source | **Fixed** | 198 files `excluded:generated`; no `architecture/*` components; rules 698 with none from it; ai_surface 142; Data lens access edges 112 to 69. Residual: `ai_enhance.component_groups` still lists the removed `architecture` id under "Documentation & Tooling" |
| O10 | Front door not linked; `llms.txt` incomplete | **Half fixed** | `llms.txt` and `ai.json` now list `orientation.json`, `support.json`, `security.json`. No link from either shell |
| O11 | No edge carries port, protocol or auth | **Unchanged** | 458 edges, all `uses`/`navigation`/`import`/`modal`/`tab`. Parser work |
| O12 | Rules lens presents 698 inferred sites as rules | **Switched off** | Rules is gone from the switcher; `?lens=rules` falls back; the data stays in the manifest with an inferred marker in the panel code |
| O13 | Escape and overlays | **Fixed** | Escape closes the trust drawer and the onboarding modal; the header is no longer blocked; the guided-paths chip is hidden while a tour is active |
| O14 | Flow lens NaN rendering | **Open, not reproduced** | 0 NaN on deep link and on lens switch, as before. Nothing in the diff addresses it |
| O15 | Phone Support panel in a 199 px scroller | **Unchanged** | heading at y=585, content in a 199 px window, External reliance 1,491 px down |
| O16 | Structure lens one node at every level | **Partly** | still one node, no edges; the panel now says "Open a level: double-click a component" |
| O17 | `core/audio` help text contradicts its description | **Unchanged** | not in the corrections file |
| O18 | Component-panel GitHub link is a directory | **Unchanged** | |
| | Support lens external reliance | **Improved** | 7 vendors (AssemblyAI and ElevenLabs added) against the key's 9; entry points 0 |
| | Search box label | **Half** | workbench says "Search"; the Overview header still says "Search everything" |
| | "Answer assembled from mapped evidence" banner | **Unchanged, low** | static; with four tours present it is not currently over a fallback |
| | `?? 0` fallbacks in `orientation.ts` | **Unchanged, latent** | fire only on a projection missing a sidecar |

## New findings on the live build

**N1. The first screen contradicts itself again, on files. HIGH.** The
Overview headline is the interpreted statement: "~161K lines of code across
751 files". The stat tile directly beneath it reads "559 files", as do the
header and the coverage chip. The prose is the 2026-08-31 enrichment; the
measurement changed when O9 excluded the committed snapshot. `orientation.json`
now stamps the statement `provenance.stale: true`, and the interface renders
no stale marker anywhere (checked on the Overview, the full-description
expansion and the trust drawer). This is the morning report's item 3 exactly:
a numeral in prose shadowing a structured field. The tours were corrected by
overlay; the interpreted statement was not, and there is still no generation
rule that binds or strips numerals.

**N2. Dangling group member. LOW.** `ai_enhance.component_groups` still names
`architecture` under "Documentation & Tooling" after the component was
excluded.

**N3. Weak evidence pointer on a new mechanism. LOW.** "iOS file protection"
cites `PRE_BETA_AUDIT.md` with signal "import/symbol". The source has it at
`UnaMentis/Core/Persistence/PersistenceController.swift:101-102`; the lens
should point there.

**N4. The corrections overlay is the right shape and the wrong long-term
home. PROCESS.** Exact-value, commit-bound, recorded in the manifest, refused
when stale: this is how a hand correction should be done, and it is not
"hand-editing March prose" in the sense the morning report warned against.
But it corrects seven sentences; the class is fixed only when generation
enforces "no numeral in prose that a field holds" and re-enrichment replaces
the vintage. N1 is the proof.

**N5. Nothing is committed.** All of this lives in the working tree of
`wt/comprehension-review-remediation`. A `git stash` or a checkout loses it.

## What this means for the three personas' complaints

Of the 28 distinct trust incidents on the three cards, 19 are fixed or
switched off on the live build, 3 are improved, 5 are unchanged (O11, O15,
O17, O18, the taxonomy split of 3 areas versus 7 groups), and 1 is new (N1).
Every high-severity incident from the run is closed. The posture gap Richard
asked about is closed on the tool's side, with the repository's own sentence
cited on the first screen, which also settles the attribution question for
this subject: once the tool carried the claim, the subject's docs were
sufficient.

Not re-checked: the Auth concern (O12's second half), the three dependency
counts' labels, and the token-economy sizes. None was in the diff.

## Recommendation before the next demo

1. Fix N1: either render the `stale` flag on the interpreted statement, or
   bind the file and line counts in it to `stats` at assembly time, or both.
   It is the first sentence a buyer reads and it disagrees with the number
   under it.
2. Commit the remediation branch, with the corrections file, before anything
   else touches that worktree.
3. Then the deferred items in order: `project.yml` and `Package.resolved` in
   the SBOM; a UI link to `llms.txt`; the phone Support ordering; the audio
   help-text contradiction via the same overlay mechanism; the dangling group
   id.
4. A rerun of the three personas is warranted only after N1 and the commit,
   and it should be a calibration run against the 2026-09-01 cards using the
   same answer key.
