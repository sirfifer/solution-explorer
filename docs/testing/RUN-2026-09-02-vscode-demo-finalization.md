# VS Code demo finalization

Finalization run for the Visual Studio Code front-door and Workbench demo on
2026-09-02. This follows `DEMO-GATE-RETURN-2026-09-02.md` and uses its exact
canonical projection. No model or enrichment call was made.

## Inputs and immutable identity

- Source repository: `https://github.com/microsoft/vscode`
- Source commit: `474a349ad5b745e512ef86b864d1c74f7264dd7a`
- Canonical projection:
  `/Volumes/Studio/dev/solution-explorer/.testboard/live/vscode-full-20260831-5f6a814/viewer-projection/architecture`
- Canonical store:
  `/Volumes/Studio/dev/solution-explorer/.testboard/live/vscode-full-20260831-5f6a814/index.db`
- Canonical manifest SHA-256:
  `f97a4cbc05f1c34ef8121b4ccf1a8dbf4d0d397f263c62dfb42fda0a4214ce4b`
- Canonical store SHA-256:
  `fe53fb0de43b4087794043bb3a6c221d6f4277d63f7d67c06b710393a77145fc`
- Projection identity: 571 components, 15,204 files, 5,453 relationships,
  four tours.

The canonical files were not modified. All generated human views and
publication material live in a derived assembly.

## Final assembly

```sh
python3 scripts/assemble-serve.py vscode \
  --projection /Volumes/Studio/dev/solution-explorer/.testboard/live/vscode-full-20260831-5f6a814/viewer-projection/architecture \
  --corrections demos/review-corrections/vscode.json \
  --publication demos/publication/vscode.json \
  --upstream-source /Volumes/Studio/dev/.demo-corpus/vscode \
  --scrub-activity --no-build
```

- Derived projection:
  `.testboard/derived/vscode/architecture`
- Served bundle:
  `.testboard/serve/vscode`
- Deterministic sidecars/material:
  `orientation.json`, `support.json`, `security.json`, privacy-scrubbed
  `activity.json`, `publication.json`, `UPSTREAM-LICENSE.txt`, and
  `ThirdPartyNotices.txt`.
- Review overlay: six exact, commit-bound edits recorded in
  `manifest.json.review_corrections`.
- Activity privacy check: no email-form string remains in either author
  identity field in the served sidecar.

## What closed the returned gate

- ELK layout executes in a Web Worker. Large lens layouts no longer block
  typing, painting, or navigation; selected/tour targets render provisionally
  while the worker finishes.
- Node selection no longer triggers layout. Desktop and phone double-click or
  double-tap drilling remain stable.
- The publication bundle suppresses the obsolete first-run Workbench modal and
  compacts the disclosure banner/footer on phones.
- Refuted relationships are excluded from graph roll-ups and security/portrait
  derivations. Uncertain edges remain visible and are explicitly styled and
  labeled as uncertain.
- Refuted findings are counted separately from unverified findings: 2,322
  total, 499 unverified, 510 refuted.
- Misleading semantic-level controls were removed; Overview and Workbench are
  still the two supported apertures.
- Component copy rejects blanks and `%placeholder%`, prefers observed
  documentation/mechanical descriptions, and visibly marks stale
  interpretation.
- Missing component type labels were added.
- Portrait grouping uses structural identity, folds a lone service into Core
  on a large repository, and keeps a deployment-provider label tied to the
  evidence-bearing component.
- Parser lookup now goes through the tree-sitter degradation guard in both
  enumeration and worker extraction paths.
- Published bundles carry the subject's license/notices and deterministic
  contributor pseudonyms. The original activity sidecar is unchanged.

## Validation

- Viewer unit tests: 652 passed.
- Viewer lint: passed.
- Viewer production build: passed; the ELK worker is emitted as a separate
  production asset.
- CI's generic build fixture now installs the shipping analyzer dependencies
  before generating architecture data. The parser guard exposed that this job
  previously depended on the runner image's accidental parser state.
- The separate architecture-generation job and opt-in live monitor now install
  that same parser tier as well; each runs on a fresh runner and therefore
  cannot inherit dependencies installed by an earlier job.
- The reusable action now installs the checked-out product with its full parser
  tier, and the `live` package profile includes parser/rules dependencies. This
  closes the same guard failure in existing downstream action and live-monitor
  consumers without weakening the parser check.
- Focused analyzer/assembly/human-view tests: 38 passed before the complete
  suite.
- Complete Python suite: 2,407 passed, five skipped, one expected failure.
  (An initial sandboxed run had 2,402 passes and five localhost-bind errors;
  the clean run used socket permission for the testboard HTTP fixtures.)
- VS Code quick Playwright crawl: 56/56, desktop Chromium and iPhone 13
  WebKit.
- VS Code full Playwright crawl: 56/56 in 4.1 minutes, including every
  component and every warranted detail tab.
- Canonical UnaMentis control quick crawl: 56/56 using the same viewer build.
- Cold browser probe: Overview and Workbench each fetched exactly
  `/architecture/manifest.json`, both entered the requested mode, and neither
  requested `architecture.json`.
- `/live-config.json` returns 404 by the documented static-mode probe design;
  it is optional live-monitor detection, not an architecture-data fallback.

## Remaining work, intentionally outside this demo gate

The deterministic reparse backlog from the return remains: native component
typing, schema/entity naming and access attribution, placeholder generation,
keyword-derived HTTP/WebSocket relationships, workflow ownership, zero-file
placeholder components, capability attribution, and splitting the very large
Workbench component. The viewer now avoids presenting the known bad outputs as
fact. A later reparse must use the repository virtual environment and can
reattach the existing enrichment with zero model calls.

Stored enrichment still contains a smaller text-quality backlog (framework
context, ten help strings derived from refuted edges, and one child-count
phrase). Current summary selection and relationship filtering prevent those
items from defining the primary demo experience; correcting the stored rows is
separate from this no-model finalization.

This bundle is marked `private-preview`. A hosted deployment must require
reviewer authentication until the publication/disclosure decision is made.

## Local review

- Overview: `http://127.0.0.1:5177/?mode=overview`
- Workbench: `http://127.0.0.1:5177/?mode=workbench`
