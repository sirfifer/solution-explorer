---
name: gui-test-cycle
description: Run the AI-operated GUI regression plan against the viewer and produce the blunt two-audience report (results.json + REPORT.md)
---

# /gui-test-cycle - GUI regression cycle

Run the vector-based GUI regression plan (viewer/tests/gui/plan/) against a
built viewer, with one AI runner shard per vector, and produce the results
contract: `results.json` (gui-results/v1) and `REPORT.md`. Design authority:
`docs/testing/GUI-REGRESSION-STRATEGY.md`. This skill holds the model policy,
the shard fan-out, the runner prompt template, and the results contract, so
invoking it is one line: "run a GUI test cycle on the dogfood" or "... and
iterate until green".

Two non-negotiables, inherited from VISION.md:

- No theater. The report says what is broken in plain words. PASS_FLAKY is
  never counted as green. Banned phrases include "mostly working", "minor
  issues remain", and any construction that rounds a FAIL up.
- The runner has no design judgment. It executes the plan literally and
  observes honestly. All interpretation happens in the orchestrator's
  ANALYZE step, never in the runner.

## Roles and models

- Orchestrator: the session model (Fable or Opus, chosen at invocation by cost
  and availability). Resolves the dataset, builds and serves, dispatches
  shards, merges results, writes REPORT.md, and owns all analysis.
- Runner: Sonnet, one subagent per vector, dispatched via the Agent tool with
  `model: "sonnet"`. Dispatch shards synchronously or in small monitored
  batches; never end the session to wait on a background child.

## The cycle (state machine)

1. TRIGGER. Goal received: "run the plan" or "run until green". If the goal is
   run-until-green, confirm the fix-iteration budget with the owner first;
   the default is report-and-stop after one run.
2. RUN. Steps below (prepare, dispatch, collect).
3. ANALYZE. Orchestrator reads results.json, clusters failures by probable
   root cause (one broken store selector can fail twenty cases; say so), and
   writes a ranked, concrete, file-level fix plan.
4. FIX. Only within an owner-approved budget. Fixes are delegated (Opus for
   structural work, Sonnet for mechanical fixes), on a worktree, with the
   normal PR protocol.
5. RERUN. Failed and blocked vectors first, then a full-plan rerun to confirm
   green (a fix can break a previously passing vector).
6. EXIT. Green: report and stop. Not green and out of budget or ideas: report
   exactly where it stands and what is recommended, never "close enough".

## RUN step 1: prepare

From the repo root (all paths below are repo-relative):

```bash
# 1. Materialize the target dataset (default: dogfood). Keys and generation
#    commands live in viewer/tests/gui/datasets.yaml.
python3 scripts/gui-datasets.py generate dogfood

# 2. Production build (this is what users get; a --dev run is for debugging only).
cd viewer && npm ci && npm run build && cd ..

# 3. Assemble the serve root (dist copy + dataset payload, baked data removed).
python3 scripts/gui-datasets.py assemble dogfood

# 4. Serve. One port PER SHARD-DATASET PAIR (see isolation below): port
#    4<vector><dataset-index>0, e.g. V1's dogfood -> 4110, V1's split-mode
#    -> 4111, V9's three datasets -> 4910, 4911, 4912. Steps 1 and 3 must be
#    repeated for EVERY dataset key the plan's cases declare (V9 and V12
#    declare degradation datasets), not just the primary.
python3 -m http.server 4110 --directory viewer/tests/gui/.serve/dogfood &
```

The serve command was verified against a real browser when this harness was
built: the production build loads both monolith and split datasets correctly
under `python3 -m http.server`, with exactly the intentional 404 probes listed
in datasets.yaml.

Create the run directory before dispatching:
`viewer/tests/gui/results/<run-id>/` with `<run-id>` =
`<UTC yyyymmdd-HHMMSS>-<dataset>`, containing `shards/` and `evidence/`.

## RUN step 2: shard isolation (load bearing)

Dark mode, annotations, selection sets, and changelog read state all persist
in localStorage, so shared storage would bleed state across shards. The design
calls for a fresh browser context per shard. The Playwright tooling available
here attaches to a running Chrome via extension and CANNOT create new browser
contexts (verified: Target.createBrowserContext is rejected). Isolation is
therefore achieved by two stacked mechanisms, which together give the same
guarantee:

1. One port per shard. localStorage is per-origin, so shards on distinct
   ports share nothing even when running concurrently.
2. Storage clear at shard start. The runner's first action after opening its
   tab is `localStorage.clear(); sessionStorage.clear()` on its origin, so a
   rerun on a reused port still starts fresh.

V13 owns the persistence assertions (state must SURVIVE a reload within its
shard) and never shares a port with another running shard.

## RUN step 3: dispatch runners

One Agent call per vector, `model: "sonnet"`, synchronous or in monitored
batches of 2 to 3. Fill the template below completely for each shard: paste
the vector's plan cases verbatim, the dataset allowlist from datasets.yaml,
the port, and the shard output path. The runner writes its shard to
`viewer/tests/gui/results/<run-id>/shards/V<n>.json` and saves evidence under
`viewer/tests/gui/results/<run-id>/evidence/`.

### Runner prompt template (paste, fill, dispatch)

```
You are a GUI test RUNNER. You execute a fixed test plan literally and
observe honestly. You have NO design judgment: never improvise around a
missing element, never decide a failure "does not matter", never retry beyond
the single permitted reattempt. Your job is literal execution and honest
observation; interpretation belongs to the orchestrator.

APP URLS (one per dataset this shard touches; "load ... for dataset 'x'"
steps use the matching URL; the first line is the shard's primary):
{PORT_MAP}
SHARD OUTPUT: {RUN_DIR}/shards/{VECTOR_ID}.json
EVIDENCE DIR: {RUN_DIR}/evidence/

TAB HYGIENE (mandatory, one-to-one open/close). Open EXACTLY ONE browser tab
for this entire shard and reuse it across every case and every dataset origin
(one tab per shard, never one per case, never one per dataset). Track it under
a shard-unique state key (e.g. state.r{VECTOR_ID}) so concurrent shards never
share or clobber a tab. As your VERY LAST action, AFTER writing the shard
file, close it: `await p.close();`. Every tab you open must be closed by you;
a shard that leaves a tab open is a defect. Never open a second tab; if the
one tab is closed or broken, that is a BLOCKED condition to record, not a
reason to open another.

TOOLING: drive the browser with mcp__playwriter__execute (Playwright in
scope). Open your one tab at the start:
  const p = await context.newPage(); state.r{VECTOR_ID} = p;
Then IMMEDIATELY, before loading the app, install capture hooks and clear
storage for EVERY origin in the port map (visit each once and clear):
  state.consoleErrors = []; state.networkErrors = [];
  p.on('console', m => { if (m.type() === 'error') state.consoleErrors.push({text: m.text().slice(0,300), url: (m.location() && m.location().url) || ''}); });
  p.on('response', r => { if (r.status() >= 400) state.networkErrors.push(r.status() + ' ' + r.url()); });
  p.on('pageerror', e => state.consoleErrors.push({text: String(e).slice(0,300), url: 'pageerror'}));
Then visit every url in the port map once and clear its storage:
  await p.goto(url); await p.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
The welcome dialog appears on each origin's first successful load after the
clear; the plan's first case per origin dismisses it explicitly, and later
cases on that origin rely on the dismissal persisting. Do not clear storage
again between cases.
Set the viewport per case BEFORE its first step:
  desktop: {width: 1440, height: 900}
  mobile: {width: 390, height: 844}
  mobile-landscape: {width: 844, height: 390}

YOUR CASES (execute in order, exactly as written):
{CASES_YAML_VERBATIM}

ACTION VOCABULARY (closed; a step outside it is a plan bug: record the case
BLOCKED at that step with a note, do not improvise):
- "load ...": goto the app URL for the named dataset (with any query string
  the step names; default dataset is the shard's primary) and wait until the
  named condition (e.g. graph rendered: at least one .react-flow__node
  visible) or 15s timeout.
- "click <label>": click the element found by user-visible label (see FINDING
  ELEMENTS). One click.
- "open <thing>": operate the control that opens the named panel/tab/overlay.
  A dropdown that is a native select element (the lens switcher is one) is
  operated by selecting the option with the named label.
- "type <text> into <field>": focus the field found by label/placeholder and
  type the text.
- "scroll to <target>": scroll the named container or element into view.
- "press and hold <target> for N ms": dispatch touchstart at the target's
  center, wait N ms, observe, then touchend. Synthetic TouchEvent dispatch
  via p.evaluate is the defined implementation (verified: it drives the
  touch-and-hold preview; the extension tooling has no native touch
  emulation).
- "press <key>": a keyboard key (p.keyboard.press), e.g. Enter; "press the
  browser back control" means p.goBack().
- "swipe <up|down> on <target>": a touch drag on the target, implemented as
  a dispatched touchstart plus a sequence of touchmove steps in the named
  direction then touchend (needed for the mobile bottom sheet, whose
  expansion is gesture-only).
- "switch viewport orientation": swap viewport width and height.
- "reload": page.reload() and wait for render.

FINDING ELEMENTS: the way a person would. By visible text, accessible role or
label, title attribute, and position, in that order (getByRole, getByText,
getByLabel, getByTitle, getByPlaceholder; icon-only controls carry their
user-visible name in title, e.g. 'View all annotations', 'Edit', 'Delete').
Prefer exact visible text from the step. NEVER use CSS
classes or DOM structure selectors except the two named in this prompt
(.react-flow__node for graph nodes and their title text for node lookup). If
the step's label matches multiple elements, use the first VISIBLE match; if it
matches none, the step cannot be performed. When the step names a container
("the detail panel tab labeled X", "the tree row", "the header button", "the
bottom navigation button"), find the container by its visible position and
role FIRST and search for the label inside it; the same word often appears as
both a component name and a tab label, and the container scope is what a
person reading the step would use.

VERDICT SEMANTICS (from the design doc, apply mechanically):
- A step that cannot be performed (element genuinely absent after a 5s wait,
  app crashed, navigation dead): the case is BLOCKED at that step number.
  Take a screenshot at the point of blockage, record step_reached, mark
  remaining assertions "not-evaluated", move to the next case.
- All steps performed: evaluate every pass_when line as a binary. All met and
  no non-allowlisted errors: PASS. Any unmet, or any non-allowlisted console
  or network error during the flow: FAIL (record which).
- RETRY RULE: on a FAIL or BLOCKED you may retry the case EXACTLY ONCE, from
  a fresh reload (reload, clear nothing else, re-run the case's steps). If
  the retry passes fully, the verdict is PASS_FLAKY (attempts: 2), never
  PASS. If the retry also fails, keep the FIRST attempt's verdict and
  details. Never a third attempt. A STATEFUL case (one whose assertions
  depend on state the case itself creates or on being the origin's first
  load, e.g. an annotation count or an unread badge) is effectively
  single-attempt: if the retry cannot satisfy the state precondition, skip
  the retry, keep the first verdict, and note "retry not applicable:
  stateful preconditions".
- Case timeout: if a single case exceeds 5 minutes of wall time, record it
  BLOCKED at the current step with a note "case timeout".

ERROR ALLOWLIST per dataset (from datasets.yaml; these are KNOWN intentional
probes and do NOT fail a case; everything else does; apply the allowlist of
the dataset the case declares):
{ALLOWLIST_BLOCK}
ENVIRONMENT NOISE (distinct from the dataset allowlists so it cannot grow
into one; console errors matching these exact patterns are automation-
environment artifacts, recorded in the audit fields but never failing a
case):
- "Unchecked runtime.lastError" (browser-extension messaging noise; caused
  the first run's only flaky verdict)
A console error whose source URL (or whose text) matches an allowlisted path
is covered by that entry. Failed requests to allowlisted paths are covered.
Reset the capture arrays at the start of each case; evaluate them at its end.

EVIDENCE: for every case, save an end-state screenshot to
{RUN_DIR}/evidence/{VECTOR_ID}.<case-number>.png (use
p.screenshot({path, fullPage: false})). For BLOCKED and FAIL, the screenshot
is taken at the moment of failure. Cases with evidence "screenshot+console"
additionally record the FULL captured console/network arrays, including
allowlisted probe entries, in the optional console_audit and network_audit
fields of the shard entry (audit trail; console_errors/network_errors stay
non-allowlisted-only so a passing case reads clean).

SHARD FORMAT: write ONE json file to SHARD OUTPUT (create parent dirs) with
the Write tool. It must validate against viewer/tests/gui/results-schema.json
case objects. Exact shape, keys in exactly this order:
{
  "vector_file": "{VECTOR_ID}",
  "cases": [
    {
      "id": "V2.1",
      "vector": "<vector slug from the case>",
      "viewport": "desktop",
      "dataset": "<the dataset the case declares>",
      "verdict": "PASS" | "PASS_FLAKY" | "FAIL" | "BLOCKED",
      "step_reached": <1-based last step successfully performed>,
      "steps_total": <count>,
      "attempts": 1 | 2,
      "assertions": [ {"text": "<pass_when line verbatim>", "outcome": "pass"|"fail"|"not-evaluated", "detail": "<what you observed, plainly>"} ],
      "console_errors": ["<non-allowlisted excerpts, empty if clean>"],
      "network_errors": ["<STATUS url, non-allowlisted, empty if clean>"],
      "console_audit": ["<screenshot+console cases only: FULL console error list including allowlisted probes; omit the key otherwise>"],
      "network_audit": ["<screenshot+console cases only: FULL failed-request list including allowlisted probes; omit the key otherwise>"],
      "evidence": ["evidence/{VECTOR_ID}.<n>.png"],
      "wall_time_seconds": <number>,
      "notes": "<optional literal observations; omit the key if none>"
    }
  ]
}
Record wall time per case yourself (Date.now() deltas in the browser via
p.evaluate are fine).

FINAL MESSAGE: after writing the shard file, reply with exactly the shard
JSON's verdict summary, one line per case: "<id> <verdict> step
<step_reached>/<steps_total>". Nothing else. Do not editorialize, do not
summarize causes, do not suggest fixes.
```

## RUN step 4: collect and merge

After all shards land:

1. Validate every shard parses and every case id from the plan appears
   exactly once across shards. A missing case is recorded BLOCKED at step 0
   with a note "runner shard incomplete", never silently dropped.
   VALIDATE EACH SHARD against viewer/tests/gui/results-schema.json (case
   objects, including the assertion outcome enum: pass, fail,
   not-evaluated) as soon as it lands. An invalid shard goes BACK to the
   same runner once (SendMessage) with the validation error, asking it to
   rewrite the file; only if the second version is still invalid does the
   orchestrator normalize it, and then the case gets a note naming what was
   normalized. Silent normalization is not allowed (first run: two runners
   drifted the enum to met/not_met and the merge hid it).
2. Merge into `results.json` per `viewer/tests/gui/results-schema.json`:
   run-level keys in schema propertyOrder, cases sorted by id (natural sort:
   vector number then case number), case keys in the schema's case
   propertyOrder. Compute the summary and the exit status: GREEN (all PASS),
   FLAKY (no FAIL or BLOCKED, at least one PASS_FLAKY), RED (any FAIL or
   BLOCKED).
3. Write `REPORT.md` in the run directory. Contract:
   - Opens with one paragraph a non-engineer can read: what is solid, what is
     broken, what is flaky, whether the product is demoable today.
   - Then per-vector detail with inline evidence links (relative paths).
   - States counts plainly: "X of Y cases pass". Names every failure by case
     id and observed behavior. PASS_FLAKY cases are listed by name in their
     own section; flaky is a first-class outcome, not a pass.
   - Banned phrases: "mostly working", "minor issues remain", and any
     construction that rounds a FAIL up.
4. TEAR DOWN, one-to-one with setup. Every resource this cycle opened is
   closed by this cycle, on a per-run cadence, not left for a later sweep:
   a. Kill the shard servers (track their task ids at launch; stop each).
   b. Browser sweep: each runner closes its own tab, but the orchestrator
      MUST verify none leaked. Run a final mcp__playwriter__execute that
      closes every remaining page:
        for (const pg of context.pages()) { try { await pg.close(); } catch (e) {} }
      A run that ends with open tabs is a defect (the first fix-engagement
      rerun leaked ~10 tabs before this rule existed). Reuse-within-a-shard
      plus close-at-shard-end plus this orchestrator sweep gives a perfect
      one-to-one: everything opened is closed.
   c. Remove the assembled serve roots and staged datasets if this was a
      one-off cycle (viewer/tests/gui/.serve and .datasets are gitignored
      scratch; regenerable). Keep them only if another cycle will reuse them
      immediately.

## Evidence retention (owner decision, 2026-07-21)

Results are local only, never committed (the results/ directory is
gitignored). Keep the latest green run and every red run; prune the rest.
When a cycle is owner-triggered, REPORT.md is pasted into the report to the
owner, not committed.

## Flake tracking (Phase 3 hook)

Three consecutive PASS_FLAKY verdicts on the same case across runs open a
Discovered-table entry in docs/remediation/TASKS.md. Until automation exists,
check the previous run's results.json by hand during merge.
