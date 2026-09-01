# Canonical UnaMentis iOS demo

The local front-door review must use the completed UnaMentis iOS full run, not
data tracked in `viewer/public` and not a baseline, canary, evaluation, or
deployment copy.

## Canonical identity

- Dataset root: `/Volumes/Studio/dev/solution-explorer/.testboard/live/unamentis-ios-full-20260830-a5717bf`
- Projection: `/Volumes/Studio/dev/solution-explorer/.testboard/live/unamentis-ios-full-20260830-a5717bf/architecture`
- Fact store: `/Volumes/Studio/dev/solution-explorer/.testboard/live/unamentis-ios-full-20260830-a5717bf/index.db`
- Run record: `/Volumes/Studio/dev/solution-explorer/.testboard/live/unamentis-ios-full-20260830-a5717bf/run`
- Repository: `https://github.com/UnaMentis/unamentis-ios`
- Commit: `a5717bf00918be39e8e5d1bbc0662ea11ebd7b9c`
- Generated: `2026-08-31T05:50:03.252151+00:00`
- Relationships: 458
- Tours: 4
- Store SHA-256: `f9db1721b1393eeb65862a5780748ce5d8878501d4dd64149d063b9b2db560d3`
- Manifest SHA-256: `c8d92a18d2176fd7b108971a8f37a47524bd69c3141d8b6649bf9008ea7935b8`

## Assembly

From this worktree, run the supported explicit-projection command:

```bash
python3 scripts/assemble-serve.py unamentis-ios \
  --projection /Volumes/Studio/dev/solution-explorer/.testboard/live/unamentis-ios-full-20260830-a5717bf/architecture
```

The final static bundle is
`.testboard/serve/unamentis-ios`. Its `architecture` entry points at the
derived projection overlay in
`.testboard/derived/unamentis-ios/architecture`. Every canonical projection
entry in that overlay is an absolute symlink back to the exact source run.
The canonical manifest therefore retains its exact SHA-256 in the served
bundle.

The source run did not contain `orientation.json`, `support.json`, or
`security.json`. Assembly generates only those three files in the derived
overlay by calling the pure builders in `analyzer.project.human_views` over
the canonical manifest and coverage documents. This process scans no source,
opens no fact store, makes no network or model call, and does not alter the
canonical projection or enrichment.

For this run the deterministic sidecar SHA-256 values are:

- `orientation.json`: `e89cc2af025fd982bc2a3a112f52def60da7fd9732ffa6cd89e9941666c92250`
- `support.json`: `eb5705b96c3361886ed11a5ce12da3b355148a7febbe52da8e1ac7dd05747d8b`
- `security.json`: `d48b49c66e091a3e62527e43f81c7fb9f5a239275776a05ec6198cfd639cb29c`

## Stale-sample isolation

The tracked March sample for `https://github.com/UnaMentis/unamentis` now lives
only at
`viewer/tests/gui/fixtures/march-unamentis-sample`. It is explicitly test data.
`viewer/public` contains no projection, monolith, `ai.json`, or `llms.txt`, so
Vite cannot bake that sample into a production build.

Assembly also strips `architecture`, `architecture.json`, root `ai.json`, and
root `llms.txt` from every serve root before linking the selected projection.
The canonical review bundle has no active stale-data path or resolvable
monolithic fallback.

## Validation contract

Before review, verify all of the following:

1. Both modes receive HTTP 200 from `/architecture/manifest.json`.
2. Both responses have manifest SHA-256
   `c8d92a18d2176fd7b108971a8f37a47524bd69c3141d8b6649bf9008ea7935b8`.
3. Repository identity is UnaMentis iOS, relationship count is 458, and tour
   count is 4.
4. No browser request targets `/architecture.json`, `viewer/public`, or the
   March fixture.
5. Switching New to Classic and Classic to New changes presentation and URL
   state without changing or reloading the dataset.
6. Production build, human-view/assembly unit tests, complete viewer tests,
   and desktop plus phone browser smoke tests pass.

Optional probes for `/live-config.json` and
`/architecture/publication.json` return 404 in this local bundle by design;
neither is an architecture-data fallback.

## Local review

- New interface: `http://127.0.0.1:5173/?mode=overview`
- Classic interface: `http://127.0.0.1:5173/?mode=workbench`
