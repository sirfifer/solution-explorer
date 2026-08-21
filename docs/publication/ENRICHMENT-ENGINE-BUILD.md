# Enrichment Engine: build architecture and task plan

Status: execution plan, written 2026-08-21 by Fable for an Opus build session.
The design of record is `ENRICHMENT-ENGINE.md` (rev 2, the ladder). Where this
document and the design conflict, **the design wins**; where either conflicts
with code reality, stop, record the conflict in the PR description, and choose
the smallest faithful resolution.

The prize at the end: `analyze.py enhance --ladder <root>` runs P0 context
through P5 determination against a real store and produces a Run Report, with
every model invocation behind the injectable invoker seam so the whole pipeline
is testable for $0.

## 0. Ground rules for the build

1. **No real model invocations.** Every phase must work against the injectable
   `Invoker` seam (`analyzer/enrich/engine.py`, the mock-without-shelling-out
   comment). Build and test entirely with canned responses and `--dry-run`
   planning modes. The first real ladder run spends the owner's Claude Max
   usage and is a separate, owner-gated event. If you believe a real invocation
   is unavoidable, stop and ask; do not run it.
2. **No Cloudflare, no deploys, no domains.** Parked by the owner. Local only.
3. **No regression, mechanically.** The pipeline is opt-in (`--ladder`, default
   off). With it off, projection output is byte-identical: `golden-corpus.py
   check flask` AND `check fastapi` must report no drift at every task
   boundary. New projection keys appear only when their enrichment rows exist
   (the overlay's no-op-when-empty discipline), so the golden corpora, which
   have no enrichment rows, never move.
4. **Environment first.** `python3 -m venv .venv-wt && .venv-wt/bin/pip install
   -e ".[all,dev]"` before anything. Without tree-sitter the parsers silently
   degrade and every number is wrong.
5. **Known baselines.** Worktree pytest posture: 1 pre-existing failure,
   `test_pruned_directory_row_stands_in_for_its_contents` (`.git` is a file in
   a worktree). Viewer vitest: 86 failures across 11 files, environment-only;
   capture the failing FILE set before and after and diff it.
6. **Writing style.** No em or en dashes as sentence interrupters, anywhere,
   including comments and docs. Use commas and periods.
7. **Delegation.** Mechanical, well-specified tasks may go to Sonnet per the
   routing table in `HANDOFF-DEMO-PROGRAM.md`; whoever delegates keeps the
   verification and checks the artifact, not the report.
8. **Cost language.** Dollar figures are API-equivalent units the CLI reports,
   metered against the owner's subscription. Never present them as money spent.
   See `ENRICHMENT-ENGINE.md` section 2.

## 1. Module architecture

All new code under `analyzer/enrich/` unless stated. Existing machinery is
reused, never forked: `engine.py` keeps the invoker, retry, cost-ceiling and
partition loop; `passes.py` keeps the verify passes; `overlay.py` keeps the
projection bridge.

| Module | New/Ext | Responsibility |
|---|---|---|
| `pipeline.py` | new | The phase seam. `RunContext` (store, root, policy, shared budget meter, invoker factory per model, run dir, rng seed), `Phase` protocol, phase registry P0ctx/P1/P2/P3/P4/P5, descent execution, the top-level `run_pipeline()` |
| `contract.py` | new | The completeness contract: the five questions, answer/evidence schemas, contract states, triggers E1-E5, escalation records, census assembly |
| `evidence.py` | new | The no-AI evidence validator: every citation checked against repo root and store (file exists, line in range, symbol present in file or symbols table, edge in edges table, doc/manifest path exists) |
| `../derive/importance.py` | new | Navigation-importance ranking: activity hotspots + relationship fan-in + entry points + size, deterministic, stable ordering. **Not added to the projection output in this build** (that would move golden baselines); persisted in the store and read by the pipeline |
| `orientation.py` | new | P1: the subject brief (identity, audience, what-matters, subject-specific criteria, weighting adjustments, idiom warnings). Stored as an enrichment row, `target_kind="subject-brief"`, plus a JSON file in the run dir |
| `ladder.py` | new | P2: rung 2a over all targets, escalation-set assembly, rung 2b (attempt + failed questions + trigger travel with the item), rung 2c with the honest-gap terminal, the census |
| `adjudicate.py` | new | P3: compact digests (label + evidence pointer, never prose), identity verdicts via the `passes.py` idiom, wiring of `verify all`, grounding spot-checks and the substitution spot-check, sampled by importance |
| `synthesis.py` | new | P4: tour authoring (`target_kind="tour"`), reuse of the existing architecture-narrative pass, lens discovery, work-order emission (capped, logged) |
| `workorder.py` | new | The work-order dataclass (scope, lens, criteria, expected_effect, budget) and its execution as a scoped pass whose results re-enter the contract and adjudication |
| `determine.py` | new | P5: criteria evaluation against the census and verdicts, done/not-done with reasoning, bounded iteration (`min_rounds` forced, `max_rounds` cap, budget-aware), work-order issuance |
| `runreport.py` | new | Run Report: JSON (schema below) + markdown renderer. Written even on partial failure |
| `prompts.py` | ext | 2a payload additions: per-question answers with evidence, self-declared uncertainty, `parser_first` (required key, may be an empty list), contract self-state |
| `overlay.py` | ext | New target kinds: `tour` rows become `arch["tours"]` matching the viewer contract exactly (`Tour {id, title, description, steps[{target,title,narration,evidence{file,line}}], provenance{derived_from_commit, stale}}`, `viewer/src/types.ts` ~line 1042); components with honest gaps gain `ai_enhance.honest_gaps: [{question, why}]` (the optional-key precedent). Both strictly no-op when no rows exist |
| `enhance_cli.py` | ext | `--ladder` flag and per-phase model flags; default path bit-for-bit unchanged |
| `scripts/demo-site.py` | ext | Registry `enrichment` block plumbed through `enhance`; Run Report lands in `demos/runs/<slug>/<date>/`; the `enrichment_quality` gate upgraded to read the census and verify verdicts (the truth instrument) with the form scorer demoted to sanity floor |

### Data shapes (canonical, keep exactly)

```jsonc
// One answer inside a component's contract block
{"claim": "...", "status": "answered|uncertain|dropped", "reason": null,
 "evidence": [{"kind": "file|symbol|edge|manifest|doc",
                "path": "src/x.ts", "line": 120, "symbol": null}]}

// Contract state per target (also the escalation record)
{"state": "grounded|escalate|honest_gap",
 "rung": "sonnet|opus|fable",
 "failed": [{"question": "purpose|mechanism|place|identity.type|identity.framework|identity.port|identity.language|next_step",
              "trigger": "E1|E2|E3|E4|E5", "note": "..."}],
 "attempt_ref": "enrichment-row-id-of-the-attempt"}

// Work order
{"scope": ["component-ids"], "lens": "...", "criteria": "...",
 "expected_effect": "form|truth|utility: what should move",
 "budget": {"max_cost_usd": 0.0, "max_targets": 0},
 "issued_by": "P4|P5", "outcome": null}
```

Contract states are stored as enrichment rows, `target_kind="contract-state"`,
`target_id=<component id>`, payload as above. The contract's answer scaffolding
stays in the store and the Run Report; it is NOT overlaid into the product.
The product receives what it receives today, plus tours, plus honest-gap
markers.

### Run Report schema (top-level keys, all required)

`identity, ledger[], census{by_state, items[]}, escalations[], work_orders[],
iterations[], parser_findings[], criteria[], determination{verdict, reasoning},
lessons[]`. Ledger rows carry phase, rung, model, targets, tokens in/out, cost
(API-equivalent), wall seconds, retries. Renderer produces `REPORT.md` beside
`report.json`.

## 2. Tasks, in order

Each task ends with: pytest green modulo the one known worktree failure, ruff
clean, both golden corpora no-drift, and a commit whose message says what
became true. Sizes are rough: S under half a day, M about a day, L more.

**T1 (M). The phase seam.** `pipeline.py` with `RunContext`, `Phase`,
`run_pipeline`, per-phase invoker factory, one shared budget meter reusing the
engine's cost-ceiling behaviour (stop launching, finish in-flight, record
skipped, exit honestly). `enhance --ladder` wired, default off, default path
byte-identical. Unit tests for the seam with mock phases.

**T2 (M). Importance ranking.** `analyzer/derive/importance.py`. Inputs from
the store: file/component activity, edge fan-in, entry points, size. Output:
per-component score and band (quintiles), deterministic and stable under
re-run. Persisted in the store (new table or meta, your call, recorded in the
module docstring). NOT in the projection. Tests on a synthetic store; golden
corpora prove no projection movement.

**T3 (M). Contract and validator.** `contract.py` + `evidence.py` with the
shapes above. The validator is pure code, no AI, and every check is
independently unit-tested against a fixture repo, including the failure modes
(missing file, out-of-range line, absent symbol, unknown edge).

**T4 (M). 2a payload.** `prompts.py` and the payload schema: per-question
answers with evidence, uncertainty, `parser_first` (required key; the prompt
states it is the FIRST question, before anything else), contract self-state.
`score-ai-enhancement-quality.py` learns to tolerate the new keys (sanity
floor; it must not gate on them). Mock-invoker tests: a canned grounded
response, a canned E1 and E5 response, a response with an uncitable claim that
the validator converts to E2.

**T5 (L). The ladder.** `ladder.py`: 2a over all targets weighted by
importance, escalation assembly, 2b receiving attempt + failed questions +
trigger (assert in tests that 2b's prompt contains the 2a attempt: the no-redo
property is a test, not a hope), 2c with honest-gap terminal, census assembly.
End-to-end mock test driving items to every terminal state including
`honest_gap`.

**T6 (L). Final adjudication.** `adjudicate.py`: digests, identity verdicts,
`verify all` wired in, grounding spot-checks sampled by importance, the
substitution spot-check (give the adjudicator a description plus three sibling
names; failure to identify the subject is an E4 confirmation; disagreement rate
recorded). Dry-run planning mode like `verify_cli`. Mock tests.

**T7 (S). Orientation.** `orientation.py`: subject brief schema and storage.
The brief's criteria list is what P5 consumes; make the coupling explicit in
types, not convention. Mock tests.

**T8 (L). Synthesis.** `synthesis.py` + overlay extension. Tours must match
`viewer/src/types.ts` exactly; validate at write time. Steps anchor to stable
ids and real file:line evidence (validator-checked). Narrative reuses the
existing architecture pass. Lens discovery emits capped work orders. Overlay
no-op-when-empty proven by tests; viewer vitest failing-file set identical to
baseline.

**T9 (M). Work orders and descent.** `workorder.py`: execution as a scoped
pass (the `include_ids` partition path exists for exactly this), results
re-entering contract and adjudication. Tests: an order's results change the
census; an order cannot spawn further orders (one level, enforced).

**T10 (L). Determination and Run Report.** `determine.py` + `runreport.py`.
Forced iteration via `iteration.min_rounds` (a forced round must carry a
reasoned target; assert it), `max_rounds` cap, budget-awareness, honest
recording of a no-gain round. Full-pipeline mock end-to-end test that produces
a complete `report.json` + `REPORT.md`; commit that artifact under
`tests/fixtures/` as the reference report.

**T11 (M). Harness and registry.** Registry `enrichment` block
(`{pipeline: "ladder", models: {...}, iteration: {min_rounds: 1, max_rounds: 2}}`)
added to `demos/registry/vscode.json` with `min_rounds: 1` per the Wave 1
forced-iteration decision. `demo-site.py enhance` plumbs it; Run Report lands
in the run dir; the `enrichment_quality` gate reads census + verify verdicts,
keeps the form scorer as floor, and keeps the NOT_IMPLEMENTED discipline (a
gate whose instrument is absent says so loudly; it never silently passes).

**T12 (S). Sweep and PR.** Full posture: pytest, ruff, both golden corpora,
viewer tsc + eslint + vitest file-set diff, `node --test
infrastructure/preview-gate/*.test.mjs` untouched. PR against main describing
what was built, what was NOT run (no real model invocations), and the exact
command the owner-gated first real run will use.

## 3. Explicitly out of scope

Real model invocations of any kind. The first real VS Code ladder run and its
calibration. Viewer rendering work beyond tour-contract compliance (honest-gap
UI is a later card). GitHub issue filing for parser findings (the 5.2
machinery is its own track; findings go to the Run Report and findings.json).
Surfacing the importance ranking in the projection or viewer. Anything
Cloudflare.
