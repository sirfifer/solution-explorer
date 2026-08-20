# N1 calibration run: how the three sittings are staffed

Decision packet, written 2026-08-18, both recommendations approved by the owner
2026-08-19; the run therefore lives under `2026-08-19`. Written before any part of N1 starts, because
staffing is not a logistics detail here. Under
`docs/quality/COMPREHENSION-REVIEW.md` the coldness of a persona *is* the
measurement, so the staffing choice decides whether the resulting number means
anything.

Charter: `comprehension-review/v1`. Subject: UnaMentis.

## What is being decided

Two things, and a third that is already forced.

1. **How the three personas are staffed.** The handoff left this open as
   "subagents or separate sessions".
2. **What the personas point at.** Recon showed the handoff's assumption here
   conflicts with a charter rule. This was not visible when the handoff was
   written.
3. Not a decision, but it constrains both: **the sittings must be sequential.**

## What recon found

Four facts, all verified first-hand today.

### F1. The browser tool is pinned to this repository

`mcp__playwriter__execute` is the only browser automation in the project, and it
is configured in `.mcp.json` at **project scope**. It is absent from
`~/.claude.json` at user scope and from both settings files. A session started
anywhere else on this machine has no browser at all.

That matters because the cleanest way to guarantee a cold persona is to start it
somewhere that cannot see this repository, and the browser it needs lives inside
the repository it must not see. The stanza is self-contained, however:

```json
{"mcpServers":{"playwriter":{"type":"stdio","command":"npx","args":["-y","playwriter@latest"],"env":{}}}}
```

No repo paths, no local build. It can be copied verbatim into an isolated
persona directory, which resolves the conflict. This is the fact that makes
option 2 below viable.

### F2. Playwriter cannot create browser contexts, so sittings are sequential

From `.claude/skills/gui-test-cycle/SKILL.md`: the tooling "attaches to a running
Chrome via extension and CANNOT create new browser contexts (verified:
`Target.createBrowserContext` is rejected)."

Every persona, however staffed, attaches to the same Chrome. Three concurrent
personas would collide on tabs and share storage per origin. Sequential is
forced under every option, so it is not a discriminator between them. Budget
three to four and a half hours of wall clock for the sittings.

### F3. The baseline was measured on a local mirror, not on the live site

The handoff says the "after" is "three live sittings against
`solution-explorer.unamentis.org`". The "before" it is compared against was not.
`docs/remediation/COMPREHENSION-STUDY-2026-08-17.md` records the method as the
demo dataset "mirrored byte-for-byte from solution-explorer.unamentis.org and
served locally under a fresh production build of `main`", each persona "on an
isolated port with cleared storage". P1's journal opens on `localhost:5310`.

So pointing the "after" at the live origin changes two variables at once, the
product and the serving method, in the one run whose entire purpose is to
validate the instrument against a single known change. It also breaks charter
rule 2, which requires one origin per persona: the live site is one origin for
all three.

The live site is reachable and healthy, `HTTP/2 200`,
`cache-control: public, max-age=0, must-revalidate`, `cf-cache-status: DYNAMIC`.
Nothing is wrong with it. It is the wrong instrument setting for this
particular run.

### F4. The retrospective baseline is thinner than the handoff assumed

At `/Volumes/Studio/dev/.evidence/solution-explorer/persona-runs/20260817/`,
28 MB total:

| Persona | Journal | Findings | Screenshots |
|---|---|---|---|
| p1 (Maya) | yes | yes | 46 |
| p2 (Doug) | yes | yes | 30 |
| p3 (Priya) | yes | **missing** | 46 |

P3's journal signs off "Full findings and grades in FINDINGS.md" and that file
does not exist. P3 therefore has no explicit battery answers, no confidence
labels, no ranked blocker list, no trust assessment and no verdict. Several of
P3's six dimensions will be `null` on a card marked `"retrospective": true`,
which the scorer accepts, and `scripts/comprehension-score.py` will then report
the run as "a FLOOR, not a score".

`minutes_to_orientation` is unsupportable as a measured value for all three. P1
offers prose only ("Ten minutes in", "roughly 75 minutes"), P2 offers section
headers only ("First five minutes", "Minutes 5-20"), P3 offers nothing. It
should be `null` across the baseline, as the charter predicted.

One scorer quirk worth knowing before the cards are authored: the evidence check
runs unconditionally, so a `null`-score dimension still requires a non-empty
`evidence` string, and the error it raises if you omit it reads "has a score but
no evidence". Note it for the instrument retro.

## Decision 1: staffing

### Option 1. Subagents from the orchestrating session

One fresh subagent per persona, Sonnet, briefed with persona, mission, battery
and URL.

- Effort: none beyond the briefs. Roughly 15 minutes of briefing per persona.
- For: cheapest and fastest. Fully orchestrated. Trivial to re-run a spoiled
  sitting. Evidence lands straight on local disk.
- Against: **the isolation is a promise, not a construction.** The subagent's
  working directory is this repository. `docs/quality/COMPREHENSION-REVIEW.md`,
  the nine known defects and the prior B+ verdict are all one `cat` away. Worse,
  this project's auto-memory index carries the line "Comprehension study
  2026-08, B+ verdict, S1-S9 findings", which is injected as context rather than
  fetched by a tool call, so it would **not** show up in a post-hoc audit of the
  persona's tool calls. Deliberate repo reads are auditable after the fact;
  that particular leak is not.

### Option 2. Isolated sessions, one per persona, outside the repository

Each persona runs as a separate headless session started in its own scratch
directory, carrying a copied `.mcp.json` that grants playwriter and nothing
else. Sonnet. Sequential.

- Effort: 30 to 45 minutes of one-time setup, plus a 10 minute smoke test to
  confirm a nested session can drive playwriter and take a screenshot. Reusable
  for every subject afterwards.
- For: **isolation by construction.** A different working directory means no
  repo file on any relative path, no project `CLAUDE.md`, and, because the
  auto-memory directory is keyed to the project path, no memory of the B+
  verdict or the S1-S9 findings. The persona's entire world is its brief, its
  port and its evidence directory. This is the version that survives a buyer
  asking "how do you know they were cold?". It is also reusable infrastructure:
  the register has eleven subjects and each one needs three cold personas.
- Against: more moving parts than option 1. Permission handling in a nested
  headless session is unproven here, which is what the smoke test is for. Less
  observable mid-sitting. If the mechanism fails, fall back to option 1 with
  the audit control.

### Option 3. The owner runs the three sittings himself

Three interactive sessions on the Mac Studio, one per persona.

- Effort: three to four and a half hours of the owner's time, plus pasting three
  briefs.
- For: unimpeachable, human-attested coldness.
- Against: spends the scarcest resource in the programme on the one task a
  machine can do honestly if it is set up correctly, and does not scale to
  eleven subjects. Typing is painful for him.

### Rejected: hybrid staffing across the three personas

Staffing P1 and P2 one way and P3 another was considered and rejected. Mixing
methods inside a single run is precisely what made the 2026-08-17 run partially
incomparable with its successor. One method per run.

### Recommendation: option 2

The whole product is a bet that a map can be trusted, and this instrument is the
evidence for that bet. An instrument whose central control is "we asked the
persona not to look" is worth much less than one where looking was impossible,
and the gap costs 30 to 45 minutes once. Option 1's leak through injected memory
cannot be closed by auditing, which is what decides it.

Option 3 is held in reserve for a subject whose score will be quoted
commercially. It is not needed for a calibration run whose purpose is to
validate the instrument.

If the smoke test fails, fall back to option 1 **with** the compensating
control: audit each persona's tool-call transcript for any read of this
repository, and disqualify the sitting outright if one appears. Record the
fallback and the control in `REVIEW.md`, because a later comparison needs to
know which method produced the number.

## Decision 2: what the personas point at

### Option A. The live origin, sequentially

All three against `https://solution-explorer.unamentis.org`, storage cleared at
the start of each sitting.

- For: exercises the real deployment, including Cloudflare routing and headers.
  P3's battery is partly about the deployed machine front door.
- Against: breaks charter rule 2 (one origin per persona). Changes the serving
  method between "before" and "after", confounding the calibration.

### Option B. A local byte-for-byte mirror on three ports, matching the baseline

Mirror what the live site currently serves, serve it on one port per persona
exactly as the 2026-08-17 run did, and separately verify the mirror against the
live origin as part of orchestrator verification.

- For: holds the method constant so the only thing that changed between before
  and after is the product, which is what a calibration run is for. Restores
  per-persona origin isolation. Removes network flake from a 90 minute sitting.
- Against: a static local server is not Cloudflare Pages. Path-based deep links
  could behave differently, so the routing mode must be confirmed rather than
  assumed before a persona relies on it.

### Recommendation: option B, with a recorded parity check

Mirror it, record the source URL, the fetch time and a content hash in the run
record, and have the orchestrator confirm the mirror matches what Cloudflare
serves. That discharges the "but is it the real site" objection without paying
the confound. This is a departure from the handoff's wording, which is why it is
being surfaced rather than absorbed.

## What is asked

1. Approve or override the staffing recommendation, option 2.
2. Approve or override the target recommendation, option B.
3. Note, no action needed: the baseline will be reported as a floor rather than
   a score, because P3's findings document did not survive.

Nothing starts until 1 and 2 are answered.
