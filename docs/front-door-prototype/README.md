# SysCorpus front-door prototype

This is a dependency-free interactive prototype for the comprehension-first SysCorpus redesign.

Run it from the repository root:

```bash
python3 -m http.server 4173
```

Then open:

```text
http://127.0.0.1:4173/docs/front-door-prototype/
```

The prototype stores its demonstration preferences under the local-storage key `syscorpus-front-door-prototype-preferences-v1`.

Supporting artifacts:

- `DESIGN-PROPOSAL.md` — rationale, lens decisions, data contracts, execution plan, and acceptance criteria.
- `MOBILE-AND-CROSS-CLIENT-EXECUTION.md` — rendered mobile assessment, immediate fixes, native interaction model, and the shared web/iOS snapshot and A/B plan.
- `GRAPH-ENGINE-EVALUATION.md` — current 2D engine decision, corrected routing integration, limits, replacement thresholds, and the shared 2D/3D scene contract.
- `orientation.v1.example.json` — proposed generated human-orientation projection.
