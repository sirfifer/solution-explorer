# License review: Visual Studio Code

Demo slug: `vscode`. Reviewed 2026-08-20. Reviewer: Claude (Opus 5), N3.
Follows `docs/publication/LICENSE-REVIEW.md` "The review, per demo", steps 1
through 7. **Not yet countersigned by the owner.**

Commit reviewed: `74d615da22fdd1992966b51551c4ef12ae5c09a4`.
Read from a full clone of `https://github.com/microsoft/vscode.git` at that
commit, not from a package index or from memory, as step 1 requires.

## 1. Upstream license, by SPDX identifier

**MIT.** `LICENSE.txt` at the repository root, "MIT License / Copyright (c) 2015
- present Microsoft Corporation", verified by reading the file at the pinned
commit.

**Note the filename.** It is `LICENSE.txt`, not `LICENSE`. Anything that globs
for a bare `LICENSE` will miss it.

**The distinction that matters here and is easy to get wrong:** the
`microsoft/vscode` *repository* is MIT. The *product* Microsoft ships as
"Visual Studio Code" is a different, proprietary-licensed binary built from this
source plus additions. We map the repository, so MIT governs everything we
redistribute. The demo must not present itself as a map of the shipped product.

## 2. Redistribution of rendered text

Permitted. MIT permits redistribution of the source and documentation text the
viewer renders in the detail panel and in evidence snippets, and requires the
copyright notice and permission notice to travel with it. Step 3 below is how
that requirement is met. No copyleft obligation attaches, so the step 2
escalation path does not apply.

## 3. Upstream license text ships in the bundle

`LICENSE.txt` must be copied into the deployed bundle as **`UPSTREAM-LICENSE.txt`**.
Mechanically enforced: `scripts/validate-publication.py --require` fails the
publish when `subject.affiliation` is `contributor` or `none` and no upstream
license file is present. Every demo-program publish uses `--require`.

## 4. NOTICE file

The repository carries **`ThirdPartyNotices.txt`** at its root, plus
`cglicenses.json`. `ThirdPartyNotices.txt` is the functional analogue of an
Apache-2.0 NOTICE file and **ships alongside `UPSTREAM-LICENSE.txt`** per step 4.

## 5. Trademark

Plain text name only: "Visual Studio Code". No Microsoft or VS Code logo,
wordmark, icon or styling that implies endorsement. The registry entry records
`subject.name` as plain text, and the showcase boilerplate's unofficial and
not-affiliated framing is required and validator-enforced.

## 6. Separability

Our viewer is PolyForm Noncommercial 1.0.0; the subject's content is Microsoft's. The bundle
keeps them separable: subject content lives under the projection data path,
`UPSTREAM-LICENSE.txt` and `ThirdPartyNotices.txt` name the subject's terms, and
nothing implies either license covers the other's material.

## 7. Record

| Field | Value |
|---|---|
| SPDX identifier | `MIT` |
| License file | `LICENSE.txt` |
| Additional notices | `ThirdPartyNotices.txt`, `cglicenses.json` |
| Commit reviewed | `74d615da22fdd1992966b51551c4ef12ae5c09a4` |
| Repository | `https://github.com/microsoft/vscode.git` |
| Reviewer | Claude (Opus 5), N3 |
| Date | 2026-08-20 |
| Owner countersignature | **Pending** |

A review is of a specific snapshot. When the demo refreshes to a new commit, the
harness records the new SHA; this review stands unless the upstream license file
changes, which `validate` should check by comparing the license file's hash
against the value recorded here.

## Consent

`DISCLOSURE-POLICY.md` applies. The registry records `consent.required: false`
and `consent.state: "n/a"` for a corporate-governance MIT subject with no
sensitivity triage hits. That is a claim the sensitivity triage must actually
confirm before publish, not an assumption, and it is a separate graduation-gate
item from this license review.
