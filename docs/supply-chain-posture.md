# Supply-chain and OSS posture (B5)

Delivered 2026-07-20. This note covers what this repo's own CI now does for
supply-chain security and OSS posture signals, the real quality numbers
measured while building it, and the specific steps that are left to a human
with repo admin access. This is about solution-explorer's own repository. It
is unrelated to `analyzer/sbom`, which is a product feature that generates an
SBOM for a repo the tool *analyzes*.

## What is implemented

- **SBOM generation in CI** (`.github/workflows/sbom.yml`): generates a
  CycloneDX 1.6 SBOM for both ecosystems in this repo on every push to main
  and every pull request. Python via `cyclonedx-py` (environment scan of the
  full `[all,dev]` install), npm via `@cyclonedx/cyclonedx-npm` for `viewer/`.
  Both SBOMs are uploaded as workflow artifacts.
- **SBOM at release time** (`.github/workflows/release.yml`, new
  `supply-chain` job): regenerates both SBOMs, attaches them as GitHub
  release assets, and generates a SLSA build provenance attestation for the
  SBOM files themselves via `actions/attest-build-provenance`.
- **SLSA provenance for the PyPI package**: the `publish-pypi` job now
  attests `dist/*` with `actions/attest-build-provenance` before publishing.
  npm already had SLSA-grade provenance through `npm publish --provenance`
  (npm's own OIDC-to-Sigstore flow), which was already in place and needed
  no change.
- **SBOM quality scoring**: every SBOM is scored with Interlynk `sbomqs`
  (NTIA and Interlynk profiles) and the table is printed to the job summary,
  both in CI and at release time. Not gating the build. See real numbers
  below.
- **OpenSSF Scorecard** (`.github/workflows/scorecard.yml`): the official
  OSSF-maintained workflow content, reused verbatim including its own action
  pins, so it keeps receiving the exact tested combination of
  `scorecard-action`, `checkout`, and `codeql-action` versions.
- **Dependabot** (`.github/dependabot.yml`, did not exist before): weekly
  updates for pip (root), npm (`viewer/`, `packages/cli/`), and
  `github-actions` (so hash-pinned actions get automated bump PRs).
- **Hash-pinned actions**: every `uses:` in every workflow in this repo
  (`ci.yml`, `architecture-viz.yml`, `live-monitor.yml`, `release.yml`, the
  two new files) is now pinned to a commit SHA with the human-readable tag
  as a trailing comment, resolved via the GitHub API against the exact tag
  each workflow already used, not upgraded to a newer major version. This
  directly targets Scorecard's Pinned-Dependencies check.
- **Job-level least-privilege permissions in `release.yml`**: `validate` and
  the `test` reusable-workflow call are now `contents: read`; `github-release`
  and `update-tags` are `contents: write` (only what creating a release and
  pushing moving tags needs); `publish-pypi` gained `attestations: write`
  for its new provenance step. Previously several jobs silently inherited
  the workflow's broad top-level permissions
  (`contents: write, id-token: write, attestations: write`) even when they
  did not need most of that. This targets Scorecard's Token-Permissions
  check.
- **SBOM completeness metadata**: `pyproject.toml` gained `license = "MIT"`,
  `license-files`, `authors`, and `[project.urls]`; `viewer/package.json` and
  `packages/cli/package.json` gained `license`, `author`, and `repository`.
  None of this existed before. It is what let the generated SBOMs pick up a
  license and a repository URL for the root component instead of leaving
  those fields empty, which is one of the concrete, verifiable improvements
  behind the score jump described below.

## Real sbomqs scores (measured locally, not a target)

Tooling used, versions pinned in CI: `cyclonedx-py==7.3.0`,
`@cyclonedx/cyclonedx-npm@6.0.0`, `sbomqs` (module
`github.com/interlynk-io/sbomqs/v2`) `v2.0.11`. All three were installed and
run locally against this repo to produce these numbers; nothing here is
estimated.

### Python SBOM (`cyclonedx-py environment --sv 1.6`, 64 components)

```
sbomqs score --profile ntia,interlynk --detailed sbom/python-sbom.json

SBOM Quality Score: 4.9/10.0  Grade: F   (Interlynk profile, the tool's default/overall)
NTIA Minimum Elements (2021): 8.5/10.0  Grade: B
```

NTIA profile detail:

| Feature | Score | Detail |
|---|---|---|
| comp_supplier | 0.0/10.0 | supplier/manufacturer missing for all 64 components |
| comp_name | 10.0/10.0 | name declared for all |
| comp_version | 9.8/10.0 | 63 of 64 |
| comp_uniq_id (PURL) | 9.8/10.0 | 63 of 64 |
| sbom_relationships | 10.0/10.0 | 15 direct dependencies declared |
| sbom_authors | 10.0/10.0 | inferred from the generation tool |
| sbom_timestamp | 10.0/10.0 | present |

### npm SBOM (`@cyclonedx/cyclonedx-npm`, viewer/, 373 components)

```
SBOM Quality Score: 5.1/10.0  Grade: D   (Interlynk profile)
NTIA Minimum Elements (2021): 8.6/10.0  Grade: B
```

Same shape: name/version/unique-ID/relationships/authors/timestamp all at or
near 10/10; `comp_supplier` at 0.0/10.0 for all 373 components.

### Why comp_supplier is 0 and what would fix it

This is the one real, honest gap. Neither `cyclonedx-py` nor
`@cyclonedx/cyclonedx-npm` populate a per-component "supplier" field from pip
or npm registry metadata; that field does not exist in a canonical,
machine-readable place in either ecosystem's package metadata (PyPI has no
supplier attribute distinct from author; npm's `package.json` `author` field
maps to CycloneDX `author`, not `supplier`, by both tools' own mapping code,
confirmed by reading `cyclonedx_py`'s source, which has no supplier or
maintainer handling at all as of `7.3.0`). Populating it for real would mean
fabricating a "supplier" for third-party packages this project does not
control, which the task instructions explicitly rule out. This is why the
default/overall score sits at D/F while the NTIA-minimum-elements profile
(the standard the task asked to target) sits at a genuine B (8.5-8.6/10).
The `Interlynk` default profile also penalizes missing checksums and missing
component-level SPDX license expressions on a chunk of transitive
dependencies, both of which are also generator-tool limitations for an
environment/lockfile scan rather than something in this repo's control. A
future improvement path exists (switching to a `requirements.txt` +
`pip download --require-hashes` flow to get real per-package checksums) but
was out of scope for this pass; noted for later.

### A known tool workaround, not a bug in this repo

`@cyclonedx/cyclonedx-npm` calls `npm ls --json --long --all` internally.
npm 10 and 11 report a false-positive "missing" error for optional native
packages that bundle their own sub-dependencies inside their own tarball
(`bundleDependencies`), for example `@tailwindcss/oxide-wasm32-wasi`. Nothing
is actually missing (`npm ci` completes cleanly and `npm ls`'s own stdout is
complete, valid JSON despite the nonzero exit code). Both workflow files pass
`--ignore-npm-errors`, which is `cyclonedx-npm`'s documented flag for exactly
this situation, with the reasoning recorded in a workflow comment next to
the step.

## OpenSSF Scorecard: honest check-by-check reasoning

The Scorecard binary itself was not run locally, on purpose: it evaluates
the *remote* GitHub state (branch protection, merged PR history, releases,
security settings), most of which only becomes real once this branch is
pushed and merged. Running it against the pre-existing remote state would
not reflect the changes in this note. Instead, the settings-dependent checks
below were verified directly against the GitHub API (read-only, no changes
made, consistent with the task's constraint not to touch repo admin
settings).

**Already passing / expected to pass, unaffected by this change:**

- License: `LICENSE` (MIT) already present.
- Security-Policy: `SECURITY.md` already present with reporting instructions.
- Binary-Artifacts: no compiled binaries checked in; only a handful of
  documentation screenshots (PNG), which is not what this check flags.
- Dangerous-Workflow: no `pull_request_target` usage and no untrusted
  `github.event.*` text interpolated into a shell command anywhere in
  `.github/workflows/`, checked directly.
- CI-Tests, Maintained, Contributors: behavioral checks based on commit and
  PR history, not fixable by a file change; this repo has active, recent
  commit history and PR-based merges already.

**Improved by this change:**

- Pinned-Dependencies: every workflow action is now hash-pinned (previously
  all were tag-pinned, e.g. `@v4`). New tool installs (`cyclonedx-py`,
  `@cyclonedx/cyclonedx-npm`, `sbomqs`) are version-pinned.
- Dependency-Update-Tool: `.github/dependabot.yml` did not exist before this
  change; now covers all three ecosystems in the repo.
- Token-Permissions: `release.yml` jobs now declare explicit least-privilege
  `permissions:` instead of several jobs silently inheriting the workflow's
  broad top-level grant.
- SBOM (Scorecard's own SBOM check, distinct from `sbomqs`): this check
  looks for a checked-in or release-attached SBOM, or the GitHub dependency
  graph. This repo now attaches a real CycloneDX SBOM to every release, in
  addition to the dependency graph GitHub already builds automatically for
  public repos.
- Signed-Releases: currently no tagged release has ever shipped from this
  repo (release credentials are gated on the owner per prior work), so this
  check has nothing to evaluate yet. Once a release ships, the new
  `actions/attest-build-provenance` step on the PyPI dist and on the release
  SBOMs, plus npm's existing `--provenance` publish, are exactly the signal
  this check looks for.

**Needs owner action (cannot be done from a local worktree, verified via the
GitHub API, not touched):**

- Branch-Protection on `main`: confirmed via
  `gh api repos/sirfifer/solution-explorer/branches/main/protection` ->
  `404 Branch not protected`. Settings > Branches > add a protection rule.
- Vulnerability alerts / Dependabot security updates: confirmed disabled via
  `gh api repos/sirfifer/solution-explorer` ->
  `security_and_analysis.dependabot_security_updates.status = "disabled"`,
  and `gh api .../vulnerability-alerts` -> 404. Settings > Code security >
  enable "Dependabot alerts" and "Dependabot security updates". This is
  separate from the Dependabot version-update config added in this change,
  which only opens PRs for outdated versions, not for known CVEs.
- Private Vulnerability Reporting: confirmed disabled via
  `gh api repos/sirfifer/solution-explorer/private-vulnerability-reporting`
  -> `{"enabled": false}`. This is a real gap: `SECURITY.md` already tells
  reporters to use "Security tab > Report a vulnerability", but that flow is
  currently off. Settings > Code security > enable "Private vulnerability
  reporting". This is a quick, high-value fix.
- OpenSSF Best Practices Badge: requires a human account at
  bestpractices.dev and a self-assessment; not something a repo checkout can
  do.
- Publishing the sbomqs score to sbombenchmark.dev: requires a human account
  there; the real numbers to submit are in this document.
- CII-Best-Practices / general registration steps: same as the badge above.

**Not implemented, flagged as future work, not part of this task's four
items:**

- SAST: Scorecard's SAST check looks for specific tools (CodeQL,
  SonarCloud, Snyk Code, Semgrep, etc.), not general linters. `ruff` and
  `eslint` run in CI but do not count. Adding a CodeQL workflow is a
  reasonable next step but was outside the four items this task asked for
  and was not added here to keep this change reviewable.
- Fuzzing: no fuzz targets exist for this project; out of scope here.

## Tools run locally and their exact versions

- `cyclonedx-py` 7.3.0, installed via `pip install cyclonedx-py==7.3.0` in a
  scratch virtualenv with this project installed as `.[all,dev]`. Ran
  successfully; output validated with `--validate` (the tool's default).
- `@cyclonedx/cyclonedx-npm` 6.0.0, run via
  `npx --yes @cyclonedx/cyclonedx-npm@6.0.0 --ignore-npm-errors` inside
  `viewer/`. Ran successfully after adding `--ignore-npm-errors` (see above).
- `sbomqs` (module `github.com/interlynk-io/sbomqs/v2`) v2.0.11, installed
  via `go install github.com/interlynk-io/sbomqs/v2@v2.0.11` (Go module
  proxy + sumdb checksum verification, no unpinned install script used). Ran
  successfully against both generated SBOMs; scores above are its real
  output, not summarized or rounded up.
- `actionlint` (latest via `go install`), used to validate every workflow
  file in `.github/workflows/` after every edit, including the pre-existing
  ones that were hash-pin-retrofitted. No new findings introduced by this
  change; the only findings anywhere are pre-existing shellcheck info-level
  notices in `ci.yml` at lines 64 and 133, in code this change did not touch.
- OpenSSF Scorecard CLI: not run locally. See the reasoning above; it
  evaluates remote repository state that does not exist until this branch
  is pushed and merged. Individual settings-dependent checks were instead
  verified with targeted, read-only `gh api` calls against the live repo,
  which is more accurate than a local Scorecard run against stale state
  would have been.

## Remaining human steps, explicit list

1. Review and merge this branch (local commits only were made; nothing was
   pushed, per instructions).
2. Enable branch protection on `main` (Settings > Branches).
3. Enable Dependabot alerts and Dependabot security updates (Settings > Code
   security).
4. Enable Private Vulnerability Reporting (Settings > Code security). This
   one directly fixes a gap between what `SECURITY.md` promises and what is
   actually turned on.
5. Register the repo for the OpenSSF Best Practices Badge at
   bestpractices.dev.
6. Submit the sbomqs scores above to sbombenchmark.dev, or re-run
   `sbomqs score` against the SBOMs produced by the first real run of
   `sbom.yml` and submit those.
7. When ready to cut a real release: the existing owner-gated items (PyPI
   trusted publishing setup, `NPM_TOKEN`, the `v1.2.0` tag push) still apply
   from prior work; once that happens, the new `supply-chain` job's
   provenance attestation and SBOM release assets will run for the first
   time end to end and should be spot-checked (`gh attestation verify`
   against the published `dist/*` and `sbom/*.json`).
8. Optional, not required by this task: add a CodeQL (or equivalent SAST)
   workflow to improve Scorecard's SAST check.
