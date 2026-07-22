# GUI regression plan and harness

AI-operated, vector-based GUI regression testing for the viewer. Design
authority: `docs/testing/GUI-REGRESSION-STRATEGY.md`. Run a cycle with the
`/gui-test-cycle` skill (`.claude/skills/gui-test-cycle/SKILL.md`), which
holds the orchestration, the runner prompt, and the results contract.

Contents:

- `plan/` holds one YAML file per vector (V1 through V13), each a list of
  cases: actions-only steps, binary pass_when assertions, explicit `covers:`
  tokens. `plan/waivers.yaml` records surfaces no Phase 1 dataset can
  exercise, each with a reason; waivers are visible decisions, not gaps.
  The cardinal rule: no case ships unwalked. Every case was executed against
  the running UI by its author before it was committed.
- `datasets.yaml` maps dataset keys to generation commands and to the
  per-dataset allowlist of KNOWN intentional console/network probes.
  Materialize and assemble with `scripts/gui-datasets.py`; serve with
  `python3 -m http.server <port> --directory viewer/tests/gui/.serve/<key>`.
- `surface.yaml` is the hand-maintained surface manifest (tier two of the
  completeness check): every component under `viewer/src/components/` is
  either a covered surface or explicitly ignored with a reason.
- `results-schema.json` is the gui-results/v1 contract for `results.json`.
- `fixtures/old-format/` is the frozen pre-gap projection (never
  regenerated); it locks the additive-projection promise at the UI level.
- `results/` (gitignored) receives one directory per run: `results.json`,
  `REPORT.md`, `shards/`, `evidence/`.
- `.datasets/` and `.serve/` (gitignored) are regenerable staging and serve
  roots.

The maintenance convention (review-blocking): any change that adds or alters
GUI surface ships its plan delta in the same PR. `scripts/gui-plan-check.py`
mechanizes the completeness half of that convention and runs in CI on viewer
changes; it cannot judge depth, but it makes silent omission impossible.

Authoring rules, learned from the first Phase 2 run:

- The dogfood dataset moves with every commit. Exact counts and component
  names may be asserted only against frozen data (the old-format fixture)
  or the stable components under tests/fixtures/; everything else uses
  ranges or structural assertions ("at least N", "a list with entries").
- Never name the ROOT component in a case: its name is the analyzed
  folder's name, which is environment-dependent (a worktree run renamed it
  and blocked a case).
- URL assertions bind to component IDS (folder-based), never display
  labels; the two differ (id `viewer` renders as label `arch-visualizer`).
- The shard-order storage convention (first case per origin dismisses the
  welcome dialog; first-load-only assertions live in the shard's first
  case) is linted by gui-plan-check, not just prose.
- Every fetch path in viewer/src must appear in datasets.yaml's
  probe_inventory; the check enforces the inventory against the code and
  the allowlists in both directions.
