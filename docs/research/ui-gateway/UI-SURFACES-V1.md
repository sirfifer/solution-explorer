# UI surfaces v1

Status: implemented vertical slice, 2026-09-04.

`ui-surfaces.json` makes a subject's real interface a first-class, evidence-linked
part of a SysCorpus view. It is an optional projection sidecar. Its absence never
changes analyzer output, and its presence never changes canonical analysis or AI
enhancement data.

## Trust boundary

A capture package contains `ui-surfaces.json` and content-addressed PNG files
under `ui-surfaces/`. Assembly validates the package before attaching it to a
derived demo overlay:

- the package repository and analyzed commit match the publication subject;
- every PNG exists, matches its SHA-256 and declared dimensions;
- `exact` means the captured runtime commit equals the analyzed commit;
- a different installed runtime must say `representative` and the viewer shows
  that fact next to the image;
- every hotspot rectangle is normalized and inside the image;
- every hotspot names a repository-relative file owned by its declared
  projection component;
- sanitization must be explicitly recorded as true.

The canonical projection, enhancement store, and source checkout are read-only.
`scripts/assemble-serve.py --ui-surfaces <package>` attaches only the validated
manifest and capture assets to its derived overlay. Derived directories carry an
ownership marker; assembly refuses to delete an unknown directory at that path.

## Coverage semantics

`clients` inventories the subject's known interface-bearing clients. Exactly one
is primary. Each is marked `captured`, `shared`, `missing`, or `unavailable`.
`shared` is a deliberate claim and should only be used after verifying that the
same capture actually represents the other client. Similarity is not enough.

Each screen records capture time, method, runtime name/version/commit, exactness,
and sanitization. Each hotspot records a stable normalized rectangle plus its
component, file, line, and optional symbol. The viewer uses the existing
file-deep-link route so a click moves from the visible interface into the Files
tab and containing symbol without inventing a second navigation system.

## Current VS Code slice

`demos/ui-surfaces/vscode` contains the primary macOS desktop workbench. It was
captured with Playwright/Electron in an isolated profile while the pinned VS Code
source workspace and `editorPart.ts` were open. Activity bar, Explorer side bar,
editor, auxiliary side bar, title bar, and status bar hand off to their actual
implementation files.

The analyzed subject is commit `474a349ad5b745e512ef86b864d1c74f7264dd7a`.
The locally installed runtime used for the capture is VS Code 1.132.0 at commit
`df53daabb18cd157bdb08c7f01c34df936cf12f4`, so the sidecar and UI label it
`representative`. The web client remains explicitly `missing`; this slice does
not silently treat the desktop image as proof of browser parity.

## Reproduction

Run the capture adapter with explicit paths:

```sh
node scripts/capture-vscode-surface.mjs \
  "/Applications/Visual Studio Code.app/Contents/MacOS/Code" \
  "/path/to/pinned/vscode" \
  "/path/to/capture-output"
```

The adapter writes `capture.png` and `regions.json`. Packaging is a reviewed
step: copy the content-addressed image, map captured regions to code evidence,
and record the runtime provenance in `ui-surfaces.json`. See `recipe.json` in
the VS Code package for the frozen viewport, source file, selectors, and
isolation choices.

## Next increments

The v1 contract intentionally supports multiple clients and screens, but today's
viewer leads with the primary client and screen. The next durable increments are
an exact capture from the analyzed VS Code build, a separately verified web
capture, screen switching for genuinely distinct states, and automated
sanitization scanning before packaging.
