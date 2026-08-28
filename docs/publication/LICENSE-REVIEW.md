# Per-demo license review

Status: adopted 2026-08-18. The review `DISCLOSURE-POLICY.md` has referenced
since 2026-07-21 without one existing. Applies to every public demo of a
codebase we do not own, and is a gate: a demo does not publish until its review
is recorded.

## Why this is not paperwork

A deployed demo does not only publish facts ABOUT a codebase. The viewer renders
the upstream README, CLAUDE.md, and documentation excerpts inside the detail
panel, and shows evidence snippets with file and line. So the deployment
redistributes third-party copyrighted text. MIT, BSD-2, BSD-3 and Apache-2.0 all
permit that and all require the notice to travel with it.

This is also diligence surface. Solution Explorer is being built to sell, and an
acquirer's counsel will look at the public marketing surface first. A documented,
respectful license and consent trail attached to demos built on other people's
code is an asset. Reconstructing it later, from memory, is not possible.

## The review, per demo

Recorded in the demo's registry entry and checked before publish.

1. **Identify the upstream license** exactly, by SPDX identifier, read from the
   repository at the pinned commit rather than from a package index or a
   memory. Record the identifier in `publication.json` as `subject.license`.
2. **Confirm it permits redistribution of the text we render.** Every permissive
   license does. For anything copyleft, stop and escalate: not because
   structural analysis is infringing, but because a company being sold gains
   nothing from a license-adjacent argument on its public marketing surface
   (`DEMO-PROGRAM.md` section 3.5 excludes AGPL and SSPL subjects from the
   published track for exactly this reason).
3. **Ship the upstream license text in the bundle** as `UPSTREAM-LICENSE.txt`.
   This is enforced, not remembered: `scripts/validate-publication.py --require`
   fails the publish when `subject.affiliation` is `contributor` or `none` and no
   upstream license file is present.
4. **Check for a NOTICE file** (Apache-2.0 projects often carry one) and ship it
   alongside if present.
5. **Trademark.** Use the project's plain text name. Never its logo, wordmark or
   any styling that implies endorsement. The showcase boilerplate's unofficial
   and not-affiliated framing is required, and is enforced: the validator rejects
   a non-owner publication whose banner, footer and disclaimers never say so.
6. **Keep our code and their content separable in the bundle.** Our viewer is
   PolyForm Noncommercial 1.0.0. Their content is theirs. Nothing in the bundle should imply our
   license covers their material, or theirs covers ours.
7. **Record the reviewer and the date** in the registry entry, with the SPDX
   identifier and the commit reviewed. A review is of a specific snapshot.

## What is mechanically enforced today

`scripts/validate-publication.py`, wired into `action.yml` (input
`require-publication`) and `build.sh` (`SE_REQUIRE_PUBLICATION=1`):

| Obligation | Enforcement |
|---|---|
| A publication has a publisher, purpose, update policy, disclaimers and access rules | Required keys, both modes |
| Provenance is real | `subject.commit` must be a git SHA, `subject.snapshot_date` an ISO date |
| The template was actually filled in | Any remaining `EDIT:` placeholder fails, reported as one clear cause |
| A non-owner publication says it is unofficial | Banner, footer or disclaimers must say so |
| A non-owner publication names the upstream license and repository | `subject.license` and `subject.repo_url` required |
| The upstream license TEXT ships | `UPSTREAM-LICENSE.txt` required in the bundle under `--require` |
| A substitution that resolves to nothing | Rejected before it renders as `[missing: path]` |

Two modes, because breaking existing installs would be a worse failure than the
one this prevents. Default validates when the file is present and warns loudly
when it is absent. `--require` makes absence fatal, and is what every demo-program
publish uses. **An invalid file always fails, in both modes**: a half-written
sidecar is worse than none, because the viewer renders partial framing.

## The flip

Neither UnaMentis installation carries a `publication.json` today (verified
2026-08-18: the URL returns 200, but that is the SPA fallback serving
`index.html`, not a file). So `require-publication` defaults to `false` and both
installs keep deploying with a loud warning. Flip the default to `true` once
those two installs carry the file. Until then the demo program passes `--require`
explicitly, so nothing published under `syscorpus.com` can be missing it.
