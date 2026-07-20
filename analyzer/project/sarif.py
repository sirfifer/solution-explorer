"""SARIF 2.1.0 exporter for the analyzer's ranked findings (A5).

Maps each store-derived finding (analyzer/derive/correlations.py duplication,
inconsistency, and unreferenced findings; analyzer/enrich/passes.py
intent-violation findings; analyzer/cra/models.py cra_readiness gap findings)
onto one SARIF result, so the same evidence-bearing findings surface the MCP
tools and the viewer read (architecture.json / manifest.json ``.findings``)
can be ingested by GitHub code scanning via ``github/codeql-action/upload-sarif``.
See docs/sarif-export.md for the exact upload workflow, which is an owner step
this module cannot perform (it requires pushing to GitHub).

Every finding kind becomes a SARIF rule (``tool.driver.rules[]``) with a fixed
default level. An unrecognized future kind falls back to a generic rule instead
of raising, so a new finding kind never breaks the export. A finding's
``verification_status`` and ``rank_score`` ride in the SARIF result properties
bag. A refuted finding is additionally represented as a SARIF suppression
(``kind: external``), so it stays visible in the log instead of being silently
dropped, matching the "never a silent drop" discipline the correlation pass
itself follows for refuted edges and findings (analyzer/enrich/verdicts.py).

Locations. A finding's ``members`` or ``evidence`` may or may not carry a
file and line: duplication members always do (a fragment's file and line
range); inconsistency and intent-violation evidence names a component, not a
line; a cra_readiness gap finding has no location at all, since an absent
artifact has nowhere in the tree to point. GitHub requires at least one
location per result, so the lookup falls back, in order, from a precise
member file+line, to evidence file+line, to an evidence-named path (line 1),
to a component's first known file resolved from the component tree (line 1),
to the repository root marker ``.`` (line 1) as the final fallback, so every
finding resolves to a location and no result is dropped for lack of one.

Paths in ``artifactLocation.uri`` are the analyzer's own repo-relative POSIX
paths verbatim: GitHub requires the uri to be relative to the repository root,
which is exactly how every path already rides in the analyzer's projected
output (invariant I4: no root-dependent absolute paths in projected data).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .. import __version__
from ..enrich.partition import flatten_components

__all__ = ["build_sarif", "write_sarif", "SARIF_VERSION", "SCHEMA_URI"]

SARIF_VERSION = "2.1.0"
SCHEMA_URI = (
    "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/"
    "sarif-schema-2.1.0.json"
)
TOOL_NAME = "solution-explorer"
INFORMATION_URI = "https://github.com/sirfifer/solution-explorer"

# One SARIF rule per finding kind (the LENS-DESIGN.md section 9 vocabulary,
# plus the P7-4 intent-violation and P10-4 cra_readiness kinds). Levels follow
# the SARIF enum (error, warning, note): an intent violation is an explicit
# conformance failure (error); duplication, inconsistency, and a missing CRA
# artifact are actionable but not failures (warning); an unreferenced
# component is the softest, most uncertain signal (note), matching its own
# summary copy ("no reference was detected", not "this is dead code").
_RULE_CATALOG: dict[str, dict] = {
    "duplication": {
        "name": "Duplication",
        "short": "Duplicate or near-duplicate code fragment",
        "full": (
            "A cross-file clone cluster detected by fingerprint matching over "
            "normalized source tokens (type-1 exact, type-2 renamed, or type-3 "
            "near-duplicate)."
        ),
        "level": "warning",
    },
    "inconsistency": {
        "name": "Inconsistency",
        "short": "Cross-cutting concern with divergent implementations",
        "full": (
            "Multiple components address the same cross-cutting concern (for "
            "example logging) with visibly different libraries or approaches."
        ),
        "level": "warning",
    },
    "unreferenced": {
        "name": "Unreferenced",
        "short": "No incoming reference was detected",
        "full": (
            "A component with no incoming edge of any kind detected by the "
            "current extractors. This is an extractor blind spot as often as "
            "it is dead code; symbol count and git churn ride as counter-"
            "evidence in the result properties."
        ),
        "level": "note",
    },
    "intent-violation": {
        "name": "IntentViolation",
        "short": "A stated architectural intent is not satisfied",
        "full": (
            "AI-verified conformance check: the code does not satisfy an "
            "intent statement recorded for this repository."
        ),
        "level": "error",
    },
    "cra_readiness": {
        "name": "CraReadiness",
        "short": "An EU Cyber Resilience Act readiness artifact is missing",
        "full": (
            "A checklist item from the CRA readiness scan (SBOM, SECURITY.md, "
            "vulnerability disclosure channel, and related supply-chain "
            "artifacts) was not found in the repository."
        ),
        "level": "warning",
    },
}
_DEFAULT_RULE = {
    "name": "Finding",
    "short": "Analyzer finding",
    "full": "A deterministic or AI-verified finding from the analyzer's correlation pass.",
    "level": "warning",
}

# GitHub requires at least one location per result (see docs/sarif-export.md).
# A finding with no file-level evidence anywhere (a repository-wide
# cra_readiness gap) is anchored at the repository root; "." is a valid
# relative-reference artifactLocation.uri per the SARIF spec (section 3.4) for
# a directory-level artifact, so the result still displays instead of being
# rejected for lacking a location.
_ROOT_MARKER = "."

# A duplication cluster can carry many member fragments. Cap the emitted
# locations per result well under GitHub's 100-displayed / 1000-total limits so
# a pathologically large cluster never produces an oversized result.
_MAX_LOCATIONS_PER_RESULT = 50


def _norm_path(path: Optional[str]) -> Optional[str]:
    """Repo-relative POSIX path, or None when there is nothing usable."""
    if not path:
        return None
    p = str(path).replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p or None


def _component_file_index(components: list) -> dict[str, str]:
    """component_id -> its first (sorted) file path, for evidence naming a
    component but not a specific file (inconsistency, intent-violation)."""
    out: dict[str, str] = {}
    for comp in flatten_components(components or []):
        files = comp.get("files") or []
        cid = comp.get("id")
        if cid and files:
            out[cid] = sorted(files)[0]
    return out


def _finding_locations(
    finding: dict, comp_files: dict[str, str]
) -> list[tuple[str, int, Optional[int]]]:
    """Return (relpath, start_line, end_line) tuples, most precise first.

    See the module docstring for the fallback order. Always returns at least
    one tuple (the repository-root marker, worst case), and never duplicates a
    (path, start, end) triple.
    """
    locs: list[tuple[str, int, Optional[int]]] = []
    seen: set[tuple[str, int, Optional[int]]] = set()

    def add(path, start, end=None) -> bool:
        p = _norm_path(path)
        if not p:
            return False
        s = int(start) if start else 1
        e = int(end) if end else None
        key = (p, s, e)
        if key in seen:
            return True
        seen.add(key)
        locs.append(key)
        return True

    # 1. Member-level file + line (duplication fragments).
    for m in finding.get("members") or []:
        if m.get("file") and m.get("line_start"):
            add(m["file"], m["line_start"], m.get("line_end"))

    # 2. Evidence-level file + line.
    if not locs:
        for e in finding.get("evidence") or []:
            if e.get("file") and e.get("line"):
                add(e["file"], e["line"], e.get("end_line"))

    # 3. Evidence-named component path (unreferenced findings), line 1.
    if not locs:
        for e in finding.get("evidence") or []:
            if e.get("path"):
                add(e["path"], 1)

    # 4. Evidence file lists (inconsistency members): one location per
    # evidence entry (its first file), line 1, so a multi-component finding
    # still points at every member, not just the first.
    if not locs:
        for e in finding.get("evidence") or []:
            for f in e.get("files") or []:
                if add(f, 1):
                    break

    # 5. Resolve a named component_id to its first known file (intent-violation
    # members, or evidence that names a component with no direct file/path).
    if not locs:
        for m in finding.get("members") or []:
            cid = m.get("component_id")
            if cid and cid in comp_files:
                add(comp_files[cid], 1)
                break
    if not locs:
        for e in finding.get("evidence") or []:
            cid = e.get("component_id")
            if cid and cid in comp_files:
                add(comp_files[cid], 1)
                break

    # 6. Last resort: the repository root, so every result has a location.
    if not locs:
        add(_ROOT_MARKER, 1)

    return locs[:_MAX_LOCATIONS_PER_RESULT]


def _sarif_location(path: str, start: int, end: Optional[int]) -> dict:
    region: dict = {"startLine": max(1, int(start))}
    if end and int(end) >= int(start):
        region["endLine"] = int(end)
    return {
        "physicalLocation": {
            "artifactLocation": {"uri": path},
            "region": region,
        }
    }


def _build_rule(kind: str) -> dict:
    spec = _RULE_CATALOG.get(kind, _DEFAULT_RULE)
    return {
        "id": kind,
        "name": spec["name"],
        "shortDescription": {"text": spec["short"]},
        "fullDescription": {"text": spec["full"]},
        "defaultConfiguration": {"level": spec["level"]},
        "properties": {"tags": ["solution-explorer", kind]},
    }


def _build_result(finding: dict, comp_files: dict[str, str], rule_idx: int) -> dict:
    kind = finding.get("kind") or "finding"
    spec = _RULE_CATALOG.get(kind, _DEFAULT_RULE)
    status = finding.get("verification_status") or "unverified"
    locations = _finding_locations(finding, comp_files)

    properties: dict = {
        "findingId": finding.get("id"),
        "verificationStatus": status,
    }
    if finding.get("rank_score") is not None:
        properties["rankScore"] = finding["rank_score"]
    if finding.get("confidence"):
        properties["confidence"] = finding["confidence"]

    result: dict = {
        "ruleId": kind,
        "ruleIndex": rule_idx,
        "level": spec["level"],
        "message": {"text": finding.get("summary") or kind},
        "locations": [_sarif_location(p, s, e) for p, s, e in locations],
        # A finding's own id is already content-derived (blake2b over its
        # evidence, invariant I4), which is exactly the stability GitHub wants
        # from a partialFingerprints value: the same underlying evidence
        # produces the same fingerprint across commits and across runs.
        "partialFingerprints": {"solutionExplorerFindingId/v1": finding.get("id") or ""},
        "properties": properties,
    }

    # A refuted finding is retained, never dropped (matching
    # analyzer/enrich/verdicts.py's own "never deleted" discipline for refuted
    # findings), but marked as a SARIF external suppression so GitHub renders
    # it as dismissed rather than as an open alert.
    if status == "refuted":
        verdict = finding.get("verdict") or {}
        reason = verdict.get("reason") or "Refuted by AI verification."
        result["suppressions"] = [{"kind": "external", "justification": reason}]

    return result


def build_sarif(arch: dict, *, analyzer_version: Optional[str] = None) -> dict:
    """Build the SARIF 2.1.0 log dict for ``arch``'s ``.findings``.

    ``arch`` is a projected architecture dict (architecture.json or
    manifest.json, already loaded): ``.findings`` is the ranked flat finding
    list, ``.components`` is the component tree used to resolve a
    component-only finding to a file. Both keys are optional; a dict with
    neither produces a valid, empty-results SARIF log.
    """
    findings = arch.get("findings") or []
    comp_files = _component_file_index(arch.get("components") or [])

    rule_index: dict[str, int] = {}
    rules: list[dict] = []
    results: list[dict] = []

    for finding in findings:
        kind = finding.get("kind") or "finding"
        if kind not in rule_index:
            rule_index[kind] = len(rules)
            rules.append(_build_rule(kind))
        results.append(_build_result(finding, comp_files, rule_index[kind]))

    return {
        "$schema": SCHEMA_URI,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": TOOL_NAME,
                        "informationUri": INFORMATION_URI,
                        "version": analyzer_version or __version__,
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }


def write_sarif(
    arch: dict, path, *, analyzer_version: Optional[str] = None, indent=2
) -> Path:
    """Build the SARIF document for ``arch`` and write it to ``path``."""
    doc = build_sarif(arch, analyzer_version=analyzer_version)
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=indent, default=str)
    return out_path
