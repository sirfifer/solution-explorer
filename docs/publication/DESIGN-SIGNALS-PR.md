# Design Signals: PR description and handoff

Status: handoff note for the owner, written 2026-08-21 by the Opus build
session that executed `DESIGN-SIGNALS-BUILD.md` tasks D0 through D8.

Branch: `wt/design-signals`, branched from `wt/enrichment-engine` (T1 through
T12), not from main. Nothing was pushed, no PR was opened, nothing was merged
or rebased. This file is the PR description for when the owner ships the
enrichment train.

## What was built

The analyzer derives the Tier 1 architecture quality signals from
`docs/research/architecture-quality-signals.md` deterministically, for any
subject, with no AI and no model spend. The viewer gained a Design lens that
presents them under the two-audience rule, blast radius became an interaction
on the graph, and the machine front door serves the same facts term-first to
agents.

| Task | What became true |
|---|---|
| D0 | The branch carries its own design sources: the research document and the build plan. |
| D1 | `analyzer/derive/design_signals.py`: fan-in, fan-out, instability, abstractness, distance from the main sequence, blast radius, churn, quintile bands, boundary strength per pair. Persisted in the store's meta table per the `importance.py` precedent. |
| D2 | Findings: cycles via iterative Tarjan, stability inversions, the two zones, cross-boundary change coupling, a boundary strength summary. Each in the dual-audience shape with copy from the translation table. |
| D3 | `--design-signals` on the analyze CLI, default off, off path byte-identical and proven so. Per-component `design` block and architecture-level `design_signals`. |
| D4 | The Design lens: gated on the dataset, ranked panel, lead-first rows with term and method chips, row-to-graph selection, the abstractness-instability scatter, edge marks with worst-case roll-up. |
| D5 | Blast radius as an interaction: client-side transitive shading both directions, count on the card. |
| D6 | `ai.json` advertisement and three MCP tools, term-first, with a test proving the two surfaces agree field by field. |
| D7 | A compact signals digest offered to P1 orientation and P4 synthesis context assembly. |
| D8 | This file, the CHANGELOG, and the full posture. |

## What the owner should look at first

**1. The language gate on abstractness (`ABSTRACTION_CAPABLE_LANGUAGES`).** This
is the largest correction the build made to the plan's assumptions, and it
changes what the feature can say about Python subjects, which is most of the
current corpus. Read the constant's comment in
`analyzer/derive/design_signals.py`. The short version: the research document
assumed the extractors distinguish abstract classes from concrete types. They do
not, in any language. Python is worse: it emits only `class` and `function`, so
an ABC, a `typing.Protocol` and a plain data holder are indistinguishable.
Without the gate every Python component computes A = 0.0, and since D = |A + I -
1| a load-bearing Python core (low instability, which is what a good core looks
like) computes D near 1.0 and gets reported in the zone of pain. That is a
confident false accusation about the most important component in the system, on
every Python codebase including both golden corpora. So abstractness is measured
only where it can be seen, and reports `null` otherwise.

The visible consequence: on flask and fastapi, abstractness is known for 0 of 23
and 0 of 120 components respectively, so those subjects get a Design lens with
cycles, inversions, blast radius, coupling and boundaries, but no scatter plot
and no zone findings. That is the correct amount to say. It is also the strongest
argument for the first follow-on below.

**2. The finding copy.** Every `lead` string is a reader-facing claim. They are
transcribed from the Part 3 translation table, but read them as a set in
`analyzer/derive/design_signals.py` and decide whether they land.

**3. The two-audience rendering.** `viewer/src/components/DesignPanel.tsx` puts
the lead first and largest and the term on a chip. Compare against
`analyzer/mcp/tools.py` `_design_finding_payload`, which inverts it. Whether the
inversion reads correctly to both audiences is a judgment call worth the owner's
eye.

## Conflicts between the plan and code reality, and how each was resolved

The build plan asked that these be recorded explicitly rather than silently
resolved. Six.

**1. The plan's edge-evidence shape is rejected by the evidence validator.** The
plan pins `{"kind": "edge", "path": null, "line": null, "symbol": null}` as the
canonical edge citation. `analyzer/enrich/evidence.py` `_check_edge` requires a
`source` and a `target` and rejects that object outright, because an all-null
citation names no edge to verify. Since the stated purpose of reusing the
contract's evidence schema is that the no-AI validator can check finding
citations, the validator wins. Edge evidence names its edge and additionally
emits the plan's three keys, so the documented shape is a strict subset of what
ships. A test proves every finding citation passes the real validator against a
real store, and that the all-null form really is rejected.

**2. The method vocabulary gained a third value.** The plan's enum is
`static-graph|git-history`. The zone-of-pain sentence in the translation table
adds a churn clause, which rests on git history while the classification itself
is structural. Part 3 requires the method chip to state which epistemic class a
claim is in, so a mixed claim needs a mixed chip. Added
`static-graph+git-history`, used only when the churn clause is actually said.
Labelling a mixed claim with the flattering half would be the quiet dishonesty
the research document is written against.

**3. Ratios are nullable; the plan's data shape implies numbers.** The canonical
per-component shape shows `"instability": 0.2, "abstractness": 0.4`. Reporting
0.0 for "not measurable" is a fabrication with consequences, as above. The keys
are kept and the values may be `null`. Every consumer branches on it, the viewer
declines to plot an unmeasured component and says how many it omitted, and the
MCP payload states the rule explicitly so an agent does not coerce it.

**4. Boundary strength ships as a summary plus an edge attribute, not per-instance
findings.** The plan's kind enum includes `boundary_strength`, which reads as one
finding per seam. The research document asks for "an edge attribute plus a
per-boundary summary", and its ranked-panel list does not include boundary
strength as a row. A row per convention-only import would be thousands of rows on
a monolith saying nothing but "this is an import". So: one summary finding, plus
the per-pair classification on `design_signals.boundaries` for the viewer's edge
rendering.

**5. Change coupling is pairwise only.** The store's `cochange_pair` table keeps
pairwise counts; the per-commit file list exists only in memory during extraction
and is discarded. The plan pre-authorized shipping coupling as a named follow-on
if extending extraction proved disproportionate. It did not: the pairwise signal
is real and useful, and it reuses the same table the Activity lens already ranks,
so the two surfaces cannot disagree. N-way "these five always ship together"
clusters would need commit-level data and are a follow-on.

**6. The word "severity" is banned from `ai.json` by an existing guard.** The
front door description originally said "no cross-kind severity ordering".
`test_findings_walk_orders_name_only_real_fields` forbids the word anywhere in
`ai.json`, because the front door once advertised a `severity` field that did not
exist and agents filtered on it and found nothing. The guard is right. The copy
moved to "no ranking of one kind against another", which says the same thing.

## Two changes with a blast radius of their own, disclosed

**`ai.json` gains one entry on every dataset.** `_MANIFEST_SECTIONS` is a static
catalog of possible top-level sections, each emitted with a `present` flag, which
is how `supply_chain`, `tours` and the rest already work. Adding `design_signals`
therefore adds one `"present": false` entry to `ai.json` for every projection,
including ones that never ran with the flag. This is additive and consistent with
the established design, the projection itself is untouched, and both golden
corpora (which diff the projection) are clean. Recorded because it is technically
a change to a published artifact on the default path.

**The MCP tool count went from nine to twelve.** Prose in four modules said
"nine". All updated. Two transport tests hardcoded `== 9`; they now assert
against `len(TOOLS)` so the next tool addition cannot drift them out of step.

## One self-inflicted mess, cleaned up, disclosed

A 2.7 MB SQLite store,
`tests/fixtures/polyglot/.solution-explorer/index.db`, was committed by
mistake in the D6 commit (`bf79f0f`) by an over-broad `git add -A`. It is a
test artifact: running the suite analyzes the fixtures, which drops a real fact
store beside each one. It is untracked on main and should never have been added.

Root cause worth fixing, and fixed: the three `.gitignore` patterns for the fact
store all contain a slash, so git anchors them to the repository root, and a
store written anywhere else escaped them entirely. `**/`-prefixed patterns now
cover nested stores, and `git check-ignore` confirms the fixture path is caught.

The file is removed from the branch tip in the final commit. **The blob is still
in the branch's history at `bf79f0f`**, because rewriting history was outside
this session's authority. If the branch is squash-merged the blob never reaches
main and nothing further is needed. If it is merged with history preserved, drop
that blob first.

## What was NOT run

- **No model invocations of any kind.** Nothing in this branch calls a model.
  Everything added is derive-tier arithmetic or rendering. The D7 digest is
  offered to the ladder's context assembly; it is not consumed by any real
  invocation, and the first real ladder run remains the owner-gated event T12
  described.
- No push, no pull request, no merge, no rebase.
- No Cloudflare, no deploy, no domain work.
- No re-baselining of either golden corpus. Neither moved, so neither needed it.

## Verification at the final boundary

- `pytest`: 2019 passed, 4 skipped, 1 xfailed, 1 failed. The single failure is
  the known worktree-only baseline,
  `test_pruned_directory_row_stands_in_for_its_contents` (`.git` is a file in a
  worktree, not a directory). The suite grew from 1926 passing at branch point.
- `ruff check analyzer/ tests/`: clean.
- `golden-corpus.py check flask` and `check fastapi`: no drift, at every one of
  the eight task boundaries.
- Viewer `tsc -b`: clean. `eslint src/`: clean.
- Viewer `vitest`: 86 failures across 11 files, the identical failing FILE set as
  the pre-existing environment-only baseline, diffed before and after. Total
  tests grew from 494 to 542.

## Named follow-ons

1. **Teach the extractors to see abstraction in Python.** Detect `abc.ABC`,
   `@abstractmethod` and `typing.Protocol` and emit a distinct symbol kind. This
   single change turns abstractness, the main-sequence scatter, and both zone
   findings on for the largest part of the current corpus. Highest value of
   anything on this list. The guard test
   `test_the_language_capability_constant_matches_what_the_parsers_emit` will
   fail the moment a parser learns a new abstract kind, which is the prompt to
   update the constant.
2. **Mark abstract classes.** No language's extractor distinguishes them today:
   TypeScript's `abstract_class_declaration`, Java's `abstract class` and a C++
   pure-virtual class all normalize to `class`. Abstractness undercounts wherever
   abstract base classes are the idiom.
3. **The opposite bias, in structurally typed languages.** In TypeScript and Go,
   `interface` declares a plain data shape at least as often as an abstraction
   contract, so a types module measures as highly abstract. Worth calibrating
   against a real subject before the scatter is put in front of a customer.
4. **Review-mode integration.** One click from a Design finding to a pre-filled
   annotation, with the finding's evidence carried across. The research document
   calls this the product's differentiator, and the plan scoped it out
   deliberately now that the lens exists to hang it on.
5. **N-way change-coupling clusters.** Needs commit-level file lists, which
   extraction currently discards after computing pairwise counts.
6. **Tier 2 signals**: over-exposure ratio, interface depth, ring discipline
   checks, boundary erosion, test seams.
7. **Content-derived finding ids.** Ids are currently `kind-rank`, which is
   stable for a given graph but shifts when the graph changes. If findings ever
   anchor annotations, they need content-derived ids like the correlations
   `findings` table already uses.
8. **The enrichment engine has no CHANGELOG entry.** T1 through T12 added no
   Unreleased lines. Design Signals now has them, which makes the omission
   visible. The owner may want to write the enrichment entries before shipping
   the train, so the release notes are not lopsided.
9. **Solution (multi-repo) mode does not carry design signals.** The
   `--design-signals` flag threads through `project_split` and `project_monolith`;
   `analyzer/solution/compose.py` calls those drivers but does not pass it, and
   the solution front door has no per-member design roll-up. Out of scope here,
   and a clean follow-on card.
