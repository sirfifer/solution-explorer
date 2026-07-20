# P10-4: EU Cyber Resilience Act, honest evaluation and recommendation

Delivered 2026-07-20. Deliverable of the P10-4 card; the owner decides.

## The CRA facts that matter (dated, sourced)

The CRA entered into force 10 December 2024. Two dates drive everything:
reporting obligations apply from 11 September 2026, and full application
(essential requirements, conformity assessment, CE marking, technical
documentation) from 11 December 2027. Reporting has no legacy grace period,
it covers products already on the market (digital-strategy.ec.europa.eu on
CRA reporting; cyberresilienceact.eu state of play).

Scope is products with digital elements made available in the EU with
commercial intent. Non-commercial open source is explicitly out of scope; a
lighter "open-source steward" category (Article 24) covers legal persons who
sustain OSS for commercial use, and stewards cannot be fined (Article
64(10)) (digital-strategy.ec.europa.eu on CRA and open source; sota.io on
steward obligations).

The obligations are overwhelmingly process and organizational, not code
artifacts: report actively exploited vulnerabilities and severe incidents to
ENISA within 24h (early warning), 72h (notification), 14 days or 1 month
(final); operate a quality system across the support period; retain an Annex
VII technical file for 10 years; affix CE marking; ship secure-by-default
configuration (Annex I and VII via cra-guide.com; goregulus.com on the
technical documentation). Penalties reach EUR 15M or 2.5 percent of global
turnover.

Only a narrow slice is a repository artifact. Annex I Part II names the
SBOM (commonly used, machine-readable, JSON or XML; CycloneDX and SPDX both
qualify though neither is mandated by name; top-level dependencies are the
floor, BSI TR-03183 and buyers push for full transitive) (scadable.com and
craevidence.com on CRA SBOM requirements). The technical file must also
reference the coordinated vulnerability disclosure policy, a contact address
for reports, and a description of secure update distribution
(finitestate.io on CRA SBOM technical documentation). In practice this maps
to a repo SECURITY.md, security.txt, and a stated support or EOL period
(complaro.com CRA checklist; provenvex.com on coordinated disclosure).

What the market already sells is telling. CRA "dashboards" in 2026 are
Snyk, Sonatype, FOSSA, Anchore, and Dependency-Track: VEX workflow,
vulnerability correlation, diffing, retention, alerting (sbom-management.com
tools survey; appsecsanta.com SBOM tools comparison). None of that is
solution-explorer's business.

## What maps to existing or carded capability

- SBOM: P10-1 already cards CycloneDX JSON per projection, transitive where
  lockfiles allow, evidence-bearing. This is the single concrete CRA code
  artifact and it is already planned.
- Hygiene findings: P10-2 already cards SECURITY.md, dependabot config,
  signed commits. security.txt and CVD contact, support-period statement,
  and update-config presence are the same class of deterministic presence
  check.
- Inventory and coverage machinery: gives EOL and pinning surfacing and the
  100 percent accounting that makes "did we miss a manifest" answerable.
- Findings surface, Rules lens, directives and sets: the delivery vehicle
  for a checklist with evidence pointers.
- Per-projection artifact pattern: ai.json, llms.txt, and the P10-1 SBOM
  already establish "emit a machine-readable file beside the site." A
  checklist artifact fits this exactly.

The tool honestly touches perhaps 3 of roughly 15 CRA obligation lines, and
those 3 are already carded. It contributes evidence; it is not a compliance
system of record.

## Three options

A. Dedicated CRA view or dashboard. Effort high (new lens, obligation
model, status rollups, ongoing regulatory maintenance as delegated and
implementing acts land). Value low to negative: it implies system-of-record
completeness the tool cannot deliver (no reporting workflow, no VEX, no
10-year retention), inviting unfavorable comparison to Snyk and FOSSA and
creating compliance-theater risk. Reject.

B. Findings-only integration. Effort low: a CRA-tagged findings pack over
P10-1 and P10-2 signals, no new surface. Value real and honest, but the
output is scattered across the findings list with no single portable
evidence object a buyer or auditor can grab.

C. Checklist artifact (emitted per projection) plus findings, no view until
pull. Effort low-plus: everything in B, plus one small cra-readiness.json
beside the SBOM enumerating each repo-observable item with present, absent,
or not-applicable and an evidence pointer. Value highest per unit effort:
it reuses the established artifact pattern, gives humans and AI a portable
structured readiness object, stays truthful by only asserting what the repo
shows, and defers the expensive view behind demonstrated customer pull.

## Recommendation

Adopt Option C. It is the honest scope: solution-explorer is an evidence
contributor to a CRA technical file, not a compliance dashboard. C reuses
machinery already carded (P10-1 SBOM, P10-2 hygiene) and the existing
per-projection artifact convention, adds almost no new surface, and refuses
the overclaim that Option A would force. A dedicated view is not justified
today and would compete in a category the product does not serve; keep it
gated behind explicit customer pull, at which point the checklist artifact
is already the data model it would render.

## Minimal first increment (if the owner says yes)

1. Land P10-1 (SBOM) first; it is the load-bearing artifact and a hard CRA
   item.
2. Add a deterministic CRA-readiness findings pack: SECURITY.md present,
   security.txt or CVD contact present, SBOM present (from P10-1), support
   or EOL statement present, update or dependency-config present. Each
   finding carries an evidence pointer or an explicit gap.
3. Emit cra-readiness.json beside the SBOM: one entry per checklist item
   with status (present, absent, NA), evidence path, and a short CRA-clause
   reference. No new view.
4. Explicitly scope-limit in output copy: repo-observable readiness only,
   not conformity, not reporting.

Stop there. Revisit a dedicated view only on real customer pull, using this
artifact as its backing model.
