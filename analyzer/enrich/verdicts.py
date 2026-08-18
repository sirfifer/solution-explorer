"""Projection overlay for AI verdicts and names (P7-3, P7-4).

The deterministic tiers (extract/derive) produce edges with a confidence tier,
concerns with mechanical slugs, and findings marked ``unverified``. The Phase 7
verification passes produce, as provenance-stamped enrichment rows:

    edge-verdict   (P7-3)  a {confirmed, refuted, uncertain} verdict per inferred
                           edge, keyed by ``source|target|type``.
    concern        (P7-4)  a domain-language {name, description} per concern,
                           keyed by concern id.
    finding        (P7-4)  an AI-generated intent-violation finding record, keyed
                           by finding id (deterministic findings are NOT stored
                           here; they live in the findings table).
    finding-verdict (P7-4) a {verification_status, reason} per finding (any kind),
                           keyed by finding id.

This module applies those rows onto the projected architecture dict at projection
time, the same shape and no-op-when-empty discipline as
``overlay.apply_enrichment_overlay``. It runs AFTER that overlay so it can read
enriched component help text if needed. Staleness is computed at read time from
the digest index and travels with each verdict (I5); a REFUTED edge or finding is
MARKED and de-emphasized, never deleted (the Phase 7 gate line, LENS-DESIGN I15).
"""

from __future__ import annotations

from typing import Optional

from .digest import DigestIndex
from .staleness import staleness_of

__all__ = ["apply_verdict_overlay"]

_VERDICT_KINDS = frozenset(
    {"edge-verdict", "concern", "finding", "finding-verdict", "identity-verdict"}
)

# Identity fields a verdict row may correct on the projected component (the S2
# gate). Kept in lockstep with passes._IDENTITY_FIELDS.
_IDENTITY_FIELDS = ("name", "type", "framework", "port")


def _stale_marker(
    verdict: dict, stale: Optional[bool], commit_sha: Optional[str]
) -> dict:
    """Attach a staleness marker to a verdict dict when the row is stale."""
    if stale is True:
        verdict["stale"] = True
        verdict["derived_from_commit"] = commit_sha
    return verdict


def apply_verdict_overlay(
    arch: dict, store, *, digest_index: Optional[DigestIndex] = None
) -> dict:
    """Overlay edge verdicts, concern names, and finding verdicts onto ``arch``.

    In place; returns ``arch``. A complete no-op when the store carries none of
    the verdict/name enrichment kinds, so a non-verified projection (and every
    parity fixture) is byte-identical to before.
    """
    if store is None:
        return arch
    rows = [r for r in store.enrichment() if r["target_kind"] in _VERDICT_KINDS]
    if not rows:
        return arch

    index = digest_index or DigestIndex.from_store(store)

    edge_verdicts: dict[str, dict] = {}
    concern_names: dict[str, dict] = {}
    ai_findings: dict[str, dict] = {}
    finding_verdicts: dict[str, dict] = {}
    identity_verdicts: dict[str, dict] = {}
    for row in rows:
        kind = row["target_kind"]
        tid = row["target_id"]
        if kind == "edge-verdict":
            edge_verdicts[tid] = row
        elif kind == "concern":
            concern_names[tid] = row
        elif kind == "finding":
            ai_findings[tid] = row
        elif kind == "finding-verdict":
            finding_verdicts[tid] = row
        elif kind == "identity-verdict":
            identity_verdicts[tid] = row

    def staleness(row: dict) -> Optional[bool]:
        current = index.for_target(row["target_kind"], row["target_id"])
        return staleness_of(row.get("derived_from_hash"), current)

    # --- identity verdicts (S2 gate) -----------------------------------------
    # Corrections are applied to the projected component with a provenance
    # marker; uncertains land in the honest-gaps record. A stale verdict is
    # NOT applied (the component's content changed since the verdict), so the
    # deterministic value stands until the next verification run.
    if identity_verdicts:
        identity_gaps: list[dict] = []

        def _apply_identity(comps: list) -> None:
            for comp in comps:
                row = identity_verdicts.get(comp.get("id"))
                if row is not None and staleness(row) is not True:
                    fields = (row.get("payload") or {}).get("fields") or {}
                    corrections: dict = {}
                    for fname in _IDENTITY_FIELDS:
                        entry = fields.get(fname) or {}
                        status = entry.get("status")
                        if status == "corrected":
                            corrections[fname] = {
                                "from": comp.get(fname),
                                "to": entry.get("value"),
                                "reason": entry.get("reason"),
                                "evidence": entry.get("evidence"),
                            }
                            comp[fname] = entry.get("value")
                        elif status == "uncertain":
                            identity_gaps.append({
                                "producer": "enrich.verify-identity",
                                "stage": f"{comp.get('id')}:{fname}",
                                "status": "unresolved",
                                "reason": entry.get("reason") or "",
                            })
                    if corrections:
                        comp["identity_corrections"] = corrections
                _apply_identity(comp.get("children", []) or [])

        _apply_identity(arch.get("components", []))
        if identity_gaps:
            gaps = arch.setdefault("gaps", [])
            existing = {(g.get("producer"), g.get("stage")) for g in gaps}
            for gap in identity_gaps:
                if (gap["producer"], gap["stage"]) not in existing:
                    gaps.append(gap)
            gaps.sort(key=lambda g: (
                g.get("producer", ""), g.get("stage", ""),
                g.get("status", ""), g.get("reason", ""),
            ))

    # --- edge verdicts (P7-3) ------------------------------------------------
    for rel in arch.get("relationships", []):
        key = "{}|{}|{}".format(
            rel.get("source", ""), rel.get("target", ""), rel.get("type", "")
        )
        row = edge_verdicts.get(key)
        if row is None:
            continue
        payload = row.get("payload") or {}
        verdict = {
            "status": payload.get("status"),
            "reason": payload.get("reason"),
        }
        _stale_marker(verdict, staleness(row), row.get("commit_sha"))
        rel["verdict"] = verdict
        # Refuted edges are marked and de-emphasized, NEVER deleted (gate line).
        if payload.get("status") == "refuted":
            rel["de_emphasized"] = True

    # --- concern names (P7-4 sub-pass 1) -------------------------------------
    if concern_names:
        for concern in arch.get("concerns", []) or []:
            row = concern_names.get(concern.get("id"))
            if row is None:
                continue
            payload = row.get("payload") or {}
            if payload.get("name"):
                concern["name"] = payload.get("name")
            if payload.get("description"):
                concern["description"] = payload.get("description")
            marker = _stale_marker({}, staleness(row), row.get("commit_sha"))
            if marker:
                concern["name_stale"] = True

    # --- AI-generated intent-violation findings (P7-4 sub-pass 2) ------------
    findings = arch.get("findings")
    if ai_findings:
        if findings is None:
            findings = []
            arch["findings"] = findings
        existing_ids = {f.get("id") for f in findings}
        for tid, row in sorted(ai_findings.items()):
            if tid in existing_ids:
                continue
            payload = row.get("payload") or {}
            record = dict(payload)
            record.setdefault("id", tid)
            record.setdefault("verification_status", "unverified")
            marker = _stale_marker({}, staleness(row), row.get("commit_sha"))
            if marker:
                record["stale"] = True
            findings.append(record)
        # Keep the ranked order (I11): rank_score desc, id.
        findings.sort(key=lambda f: (-float(f.get("rank_score") or 0.0), f.get("id") or ""))

    # --- finding verdicts (P7-4 sub-pass 3) ----------------------------------
    if finding_verdicts and findings is not None:
        by_id = {f.get("id"): f for f in findings}
        for tid, row in finding_verdicts.items():
            finding = by_id.get(tid)
            if finding is None:
                continue
            payload = row.get("payload") or {}
            status = payload.get("verification_status")
            if status:
                finding["verification_status"] = status
            verdict = {"reason": payload.get("reason")}
            _stale_marker(verdict, staleness(row), row.get("commit_sha"))
            finding["verdict"] = verdict
            # Refuted findings are retained and de-emphasized, never dropped.
            if status == "refuted":
                finding["de_emphasized"] = True

    return arch
