# SARIF export (A5)

The analyzer can write its findings (duplication, inconsistency, unreferenced,
intent-violation, cra_readiness) as a SARIF 2.1.0 log, the standard OASIS
format GitHub code scanning ingests. This document covers what the analyzer
produces, what conforms already, and the one remaining step only a repository
owner can take: uploading the file to GitHub.

## What findings map to what

Findings come from `analyzer/derive/correlations.py` (duplication,
inconsistency, unreferenced), `analyzer/enrich/passes.py` (AI-verified
intent-violation), and `analyzer/cra/models.py` (cra_readiness gaps). Each
finding kind becomes one SARIF rule, and each finding becomes one SARIF
result:

| Finding kind       | SARIF level | Meaning |
|---------------------|-------------|---------|
| `intent-violation`  | error       | An AI-verified conformance check failed. |
| `duplication`        | warning     | A cross-file clone cluster. |
| `inconsistency`       | warning     | A cross-cutting concern with divergent implementations. |
| `cra_readiness`        | warning     | A CRA readiness artifact (SBOM, SECURITY.md, and so on) is missing. |
| `unreferenced`        | note        | No incoming reference was detected; often an extractor blind spot rather than dead code. |

A finding's `verification_status` and `rank_score` ride in the result's
`properties` bag. A `refuted` finding is kept, never dropped, and additionally
carries a SARIF `suppressions` entry so GitHub renders it as dismissed instead
of as an open alert. This mirrors the "never a silent drop" rule the
correlation pass already follows for refuted findings and edges.

A finding's location comes from its most precise available evidence: a
duplication fragment's exact file and line range, an evidence entry's file and
line, a named component's path, or, for a fully repository-level finding such
as a missing SECURITY.md, the repository root (`.`) at line 1. Every result
carries at least one location, which GitHub requires to display a result.

The exporter lives in `analyzer/project/sarif.py`; see its module docstring
for the full location fallback chain and rule catalog.

## Generating a SARIF file

```
python3 analyze.py . -o architecture.json --sarif findings.sarif
```

`--sarif PATH` works with the default v2 engine (findings are a v2/Tier-3
feature). Passing it with `--engine v1` or `--incremental` (both legacy
scanner paths that never compute findings) still writes a valid, empty SARIF
log, with a warning on stderr, so a CI step that expects the file to exist
does not break depending on which engine ran.

The `--config` legacy multi-repo path is out of scope for this pass: it
merges architectures from several per-repo in-memory stores and does not
currently carry a findings surface, so a SARIF export from that path is also
empty. The primary single-repo and `--solution` composed paths are unaffected.

## Conformance to GitHub's SARIF requirements

The generated file satisfies GitHub's documented code-scanning requirements
(https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/sarif-support-for-code-scanning):

- `version` is `2.1.0` and `$schema` points at the OASIS schema.
- `tool.driver.name` and `tool.driver.rules[]` are present, one rule per
  finding kind that actually appears.
- Every result carries `message.text`, at least one `locations[]` entry with
  an `artifactLocation.uri` that is a repository-relative path (the analyzer's
  own paths already are), and a `partialFingerprints` entry built from the
  finding's own content-derived id, which is stable across runs on unchanged
  evidence.

It has been validated against the committed OASIS SARIF 2.1.0 JSON Schema
fixture (`tests/fixtures/sarif/sarif-schema-2.1.0.json`, mirrored from
https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json)
in `tests/test_sarif.py`, both for hand-built fixtures covering every finding
kind and for a real end-to-end run through the CLI.

## The remaining step: uploading to GitHub (owner action)

Actually surfacing results in a repository's Security tab requires pushing a
workflow to GitHub and letting it run there; this cannot be verified from a
local worktree. Add a step like this to a workflow that already runs
`analyze.py` (for example `.github/workflows/architecture-viz.yml`):

```yaml
permissions:
  contents: read
  security-events: write   # required by upload-sarif

steps:
  - name: Run Architecture Analyzer with SARIF export
    run: |
      python3 analyze.py . -o viewer/public/architecture.json --compact \
        --sarif findings.sarif

  - name: Upload SARIF to code scanning
    uses: github/codeql-action/upload-sarif@v3
    with:
      sarif_file: findings.sarif
      category: solution-explorer-findings
```

`security-events: write` is required on the job (or workflow) for
`upload-sarif` to write results. `category` distinguishes this upload from any
other SARIF-producing tool (for example CodeQL itself) so the two do not
overwrite each other's alerts.

After that workflow runs on the default branch, findings appear under the
repository's Security tab, Code scanning alerts. This step is owner-gated
(it requires pushing to GitHub and enabling code scanning on the target
repository) and has not been performed as part of this change.
