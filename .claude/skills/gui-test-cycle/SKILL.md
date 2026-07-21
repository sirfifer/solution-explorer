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

# 4. Serve. One port PER SHARD (see isolation below). Ports 41NN by vector
#    number, e.g. V1 -> 4101, V13 -> 4113.
python3 -m http.server 4101 --directory viewer/tests/gui/.serve/dogfood &
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

APP: http://localhost:{PORT}/  (serving the "{DATASET}" dataset)
SHARD OUTPUT: {RUN_DIR}/shards/{VECTOR_ID}.json
EVIDENCE DIR: {RUN_DIR}/evidence/

TOOLING: drive the browser with mcp__playwriter__execute (Playwright `page`
in scope). Open your OWN tab once at the start:
  const p = await context.newPage(); state.p = p;
Then IMMEDIATELY, before loading the app, install capture hooks and clear
storage for your origin:
  state.consoleErrors = []; state.networkErrors = [];
  p.on('console', m => { if (m.type() === 'error') state.consoleErrors.push({text: m.text().slice(0,300), url: (m.location() && m.location().url) || ''}); });
  p.on('response', r => { if (r.status() >= 400) state.networkErrors.push(r.status() + ' ' + r.url()); });
  p.on('pageerror', e => state.consoleErrors.push({text: String(e).slice(0,300), url: 'pageerror'});
  await p.goto('http://localhost:{PORT}/'); await p.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
Set the viewport per case BEFORE its first step:
  desktop: {width: 1440, height: 900}
  mobile: {width: 390, height: 844}
  mobile-landscape: {width: 844, height: 390}

YOUR CASES (execute in order, exactly as written):
{CASES_YAML_VERBATIM}

ACTION VOCABULARY (closed; a step outside it is a plan bug: record the case
BLOCKED at that step with a note, do not improvise):
- "load ...": goto the app URL (with any query string the step names) and
  wait until the named condition (e.g. graph rendered: at least one
  .react-flow__node visible) or 15s timeout.
- "click <label>": click the element found by user-visible label (see FINDING
  ELEMENTS). One click.
- "open <thing>": click the control that opens the named panel/tab/overlay.
- "type <text> into <field>": focus the field found by label/placeholder and
  type the text.
- "scroll to <target>": scroll the named container or element into view.
- "press and hold <target> for N ms": pointerdown on the target, wait N ms,
  pointerup (the mobile touch-and-hold path).
- "switch viewport orientation": swap viewport width and height.
- "reload": page.reload() and wait for render.

FINDING ELEMENTS: the way a person would. By visible text, accessible role or
label, and position, in that order (getByRole, getByText, getByLabel,
getByPlaceholder). Prefer exact visible text from the step. NEVER use CSS
classes or DOM structure selectors except the two named in this prompt
(.react-flow__node for graph nodes and their title text for node lookup). If
the step's label matches multiple elements, use the first VISIBLE match; if it
matches none, the step cannot be performed.

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
  details. Never a third attempt.
- Case timeout: if a single case exceeds 5 minutes of wall time, record it
  BLOCKED at the current step with a note "case timeout".

ERROR ALLOWLIST for this dataset (from datasets.yaml; these are KNOWN
intentional probes and do NOT fail a case; everything else does):
{ALLOWLIST_BLOCK}
A console error whose source URL (or whose text) matches an allowlisted path
is covered by that entry. Failed requests to allowlisted paths are covered.
Reset the capture arrays at the start of each case; evaluate them at its end.

EVIDENCE: for every case, save an end-state screenshot to
{RUN_DIR}/evidence/{VECTOR_ID}.<case-number>.png (use
p.screenshot({path, fullPage: false})). For BLOCKED and FAIL, the screenshot
is taken at the moment of failure. Cases with evidence "screenshot+console"
additionally get their captured console/network arrays written into the shard
entry even when allowlisted-only (for audit).

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
      "dataset": "{DATASET}",
      "verdict": "PASS" | "PASS_FLAKY" | "FAIL" | "BLOCKED",
      "step_reached": <1-based last step successfully performed>,
      "steps_total": <count>,
      "attempts": 1 | 2,
      "assertions": [ {"text": "<pass_when line verbatim>", "outcome": "pass"|"fail"|"not-evaluated", "detail": "<what you observed, plainly>"} ],
      "console_errors": ["<non-allowlisted excerpts, empty if clean>"],
      "network_errors": ["<STATUS url, non-allowlisted, empty if clean>"],
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
4. Kill the shard servers.

## Evidence retention (owner decision, 2026-07-21)

Results are local only, never committed (the results/ directory is
gitignored). Keep the latest green run and every red run; prune the rest.
When a cycle is owner-triggered, REPORT.md is pasted into the report to the
owner, not committed.

## Flake tracking (Phase 3 hook)

Three consecutive PASS_FLAKY verdicts on the same case across runs open a
Discovered-table entry in docs/remediation/TASKS.md. Until automation exists,
check the previous run's results.json by hand during merge.
