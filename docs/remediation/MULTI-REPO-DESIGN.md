# Multi-repo unification design (draft for the post-campaign phase)

Status: DESIGN ONLY (2026-07-20). The owner directed that multi-repo work waits
until the single-repo state is healthy, and that no throwaway code lands ahead
of this design being agreed. This document is the safe portion: it fixes the
shape so the eventual execution phase starts from decisions, not questions.
Nothing here changes runtime behavior.

## The product truth this must serve

Real solutions span repositories: one or more clients (unamentis-ios, a web
client) plus one or more servers (unamentis) form ONE product. The tool must
let a person or an AI explore the solution as a whole AND open any member repo
alone, with the same uncompromising totality per repo (100 percent, ledgered,
exceptions loud) that the single-repo engine now delivers.

## Standing constraints (all already binding)

- I1/I9: deterministic skeleton, no AI at parse or query time.
- I2: every file in every member repo accounted for exactly once, per repo.
- I4: byte-stable output; composition must not introduce order sensitivity.
- I6: incremental by construction; a solution rebuild must reuse warm member
  stores untouched.
- The frozen symbol ID grammar already namespaces by repo (`repo:` prefix);
  composition must never rewrite member IDs, only prefix-qualify where a
  member was analyzed standalone.

## Design decisions (the ones that matter)

1. **The member repo store stays the unit of truth.** No merged store. A
   solution is a COMPOSITION over per-repo fact stores, each built by the
   existing single-repo engine, each independently warm and incremental. This
   preserves I6 trivially and keeps the failure domain per repo.

2. **A solution manifest, not a config bolt-on.** `solution-explorer.solution/v1`
   (YAML, one file, human-authored): solution name, member list (path or git
   URL + optional pinned ref), per-member display label, and the optional
   cross-repo hints section (see 4). This replaces the legacy multi-repo
   `--config` JSON, which is retired at the same time v1 goes (its
   known limitations: no unified ledger, cold per run, no activity or
   capabilities or entities, are exactly what this design removes).

3. **Unified projection = concatenation plus a solution layer, never a blend.**
   Each member's projection is emitted exactly as the single-repo engine
   would (same bytes, same shards, under `members/<repo>/`). The solution
   layer adds: a solution manifest.json (member index, solution-level stats
   summed honestly, the member coverage ledgers referenced not copied), a
   solution front door (ai.json walk orders that teach an agent to descend
   into members), and the cross-repo edge set (4). The viewer opens a member
   AS IF standalone (same-element-every-lens holds) or the solution view
   (members as top-level nodes, cross-repo edges between them).

4. **Cross-repo edges are evidence-bearing derivations, never guesses.** The
   first tier is the one that pays for the whole feature: client HTTP/WS
   calls matched to server routes. Both halves already exist as signals
   (capabilities detect routes on 9 web + 4 CLI frameworks; client-side call
   sites are extractable signals). Matching is deterministic (path template
   plus method), each edge carries both file:line evidences and a confidence,
   and unmatched calls/routes surface as findings (an unconsumed endpoint and
   an unserved call are both real discoveries). The solution manifest hints
   section can pin ambiguous base URLs to members; hints are data, ledgered
   as provenance on the edge.

5. **Coverage and inventory stay per repo, summed transparently.** The
   solution badge reads like: "3 repos, 100 percent of source analyzed in
   each (1,941 files); 120 non-source accounted for across members". One
   member with gaps turns exactly that member amber in the member index.
   No blended denominator, ever: a healthy client must not dilute a gapped
   server.

6. **Knowledge layers compose in the same order everywhere.** Per-member
   `.solution-explorer/rules/` apply to that member. A solution-level
   `rules/` (beside the solution manifest) applies to all members, BELOW
   member rules in precedence (member beats solution beats built-in),
   completing the hierarchy the P6-12 loader already scaffolds (its ordered
   source list gets its second real entry here; the org level remains the
   third slot).

7. **Enrichment and tours run per member, then one solution pass.** Member
   enrichment is exactly today's DPEA. The solution pass enriches only the
   solution layer (member one-liners, cross-repo edge verdicts, solution
   tours that hop members). Provenance digests already compose (per-member
   digest plus a solution digest over the member digests).

## Phasing for the execution phase (each independently shippable)

- M1: solution manifest + composed projection with member index and summed
  coverage/inventory (no cross-repo edges yet). Viewer: member switcher,
  solution badge, member drill-in identical to standalone.
- M2: cross-repo HTTP/route edges with evidence, plus the unmatched-endpoint
  and unserved-call findings.
- M3: solution front door + MCP over the composition (the nine tools grow a
  member dimension).
- M4: solution-level rules, enrichment pass, and tours.
- Retire the legacy multi-repo --config path (with the v1 engine deletion
  card, post-demo, as already recorded).

## Explicitly out of scope until M1 lands

Cross-repo clone detection, shared-symbol identity across repos (a vendored
copy of a client SDK in the server repo is a finding, not an identity), and
any merged-store optimization. Each is listed so nobody builds it by
accident inside M1.

## Acceptance for this document

The owner reads it, adjusts what he disagrees with, and the execution phase
cards (M1-M4) get cut from the agreed version. The unamentis pair
(unamentis + unamentis-ios) is the canonical fixture for every milestone.
