# Verification queue

Every load-bearing claim the orchestrator must check independently before any
number in this run is published. Written during the run, worked after the
sittings finish, because the browser is held by the sittings one at a time.

Convention from the 2026-08-17 study, retained: **VERIFIED** means a root cause
was found. **CONFIRMED** means reproduced or corroborated but not root-caused.

## V1. The graph visualization never rendering for P1. PRIORITY.

**Claim.** P1: "Graph view toggle. Present in the DOM/breadcrumb, never had a
clickable bounding box in any state I reached. Never got a node-and-edge
visualization to render."

**Why it is load bearing.** The 2026-08-17 personas plainly had a working
canvas: P2's baseline findings describe cluster expansion producing "an
unreadable exploded view", "panel/canvas desync", and tappable nodes on mobile.
If the canvas is now unreachable, that is a regression introduced between the
baseline and now, in the same window as the comprehension fixes, and it would be
a more serious finding than anything the run set out to measure.

**Already excluded: the mirror.** The bundle's only dynamic import is
`./elk.bundled-Br0wH5XZ.js`, the ELK layout engine. That chunk is present in the
mirror and its sha256 matches the live origin exactly. No other referenced asset
is missing. An earlier apparent miss, `solution-explorer.js`, was a regex
artifact: the string in the bundle is `solution-explorer.json`, UI help text
naming a config file, and the live origin returns the SPA shell for it.

**Hypothesis to test first.** PR #96 changed snap zoom. A viewport or fit-zoom
regression could leave the canvas mounted but with no clickable bounding box,
which matches P1's wording precisely: present in the DOM, not clickable.

**How to settle it.** Drive the live origin and the mirror side by side. Check
whether the canvas mounts, whether it has non-zero dimensions, and whether the
control P1 looked for is reachable. Distinguish three outcomes, because they
have very different consequences:
1. The canvas is genuinely broken. A regression, and the most important finding
   of the run.
2. The canvas works but its control is undiscoverable. A navigation defect,
   scored under advertised paths, not a rendering bug.
3. It works and P1 simply missed it. Scored against P1, not against the product.

**Do not score `advertised_paths` for any persona until this is settled**, since
the same control is likely to affect all three.

## V2. The external dependency contradiction

**Claim.** P1: the Inventory lens counts "5 external dependencies" (OpenAI,
Anthropic, Deepgram, GitHub, Groq) while the home-page Flow narrative, generated
by the same tool, names ElevenLabs, Piper, Chatterbox and Ollama.

**Status.** Corroborated from two independent directions already. The
difficulty-profile measurement independently found exactly five named external
services in the dataset, and `ai.json` marks the supply-chain and SBOM section
`present: false`. Independent reading of the subject's own source found more
still: Google, AssemblyAI, Unleash and LiveKit appear in none of the tool's
surfaces.

**Still to settle.** Whether the five-count is a deliberate definition, external
SaaS with a network dependency only, or an incompleteness. P1 was scrupulous and
recorded it as unverified rather than false. Resolve from the analyzer source
and record which it is, because that decides whether this is a defect or a
labelling problem.

## V3. Symbol-level search degrading to file navigation

**Claim.** P1: clicking a symbol result in the command palette navigated to a
parent file or folder rather than the symbol, reproducibly, for
`AudioWebSocketHandler` and `IdleManager`.

**How to settle it.** Reproduce both directly. If confirmed, check the search
shard payload to see whether symbol results carry a target the UI is discarding,
which separates a data defect from a UI defect.

## V4. The two subject self-contradictions, checked whether or not a persona raises them

Per `ANSWER-KEY.md`. Both are unscoreable for personas and diagnostic for us.

- **USM Core's port.** Source says `8767` in the Rust CLI default and `8787` in
  a Swift client and the prose docs. If the tool states one as settled fact with
  no hedge, that is a trust incident. If it surfaces the disagreement or marks
  it inferred, that is a strength and should be recorded as one.
- **Which iOS tree is authoritative.** The two repositories' READMEs contradict
  each other. Same test.

## V5. The single-laptop fact, checked regardless of what P2 says

Per pre-registered expectation E3. The subject's own infrastructure document
names its production host as one laptop and lists "Single point of failure"
among that host's disadvantages, verbatim. Establish whether any route through
the tool leads an executive to it. The baseline P2 did not reach it and was
scored `wrong` on that question, so this is already a live concern rather than a
hypothetical one.

## V6. Whether the coverage ledger is advertised anywhere in the UI

Per pre-registered expectation E2. The ledger does not exist: no `coverage` key
in the manifest, `present: false` in `ai.json`, and `/architecture/coverage.json`
resolves to the SPA shell on the live origin. The baseline P1 already recorded
seeing "Coverage unavailable for this dataset" while the tour promised a Testing
story. If the interface still promises coverage it cannot deliver, that is a
blocked path.
