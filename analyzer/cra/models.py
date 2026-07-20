"""Data model for the CRA readiness checklist (P10-4, Option C).

The checklist is a flat list of ``CraItem`` records plus the mandatory scope
copy. Each item is one deterministic presence/absence check against
repository-observable artifacts (SECURITY.md, a disclosure contact, the emitted
SBOM, an update-config, a support statement, a signed-commit sample). The model
carries no clock and no random source: given the same repository state it
serializes byte-for-byte identically (invariant I4), matching the sbom.json
convention this artifact sits beside.

Scope, stated once here and echoed into the artifact and every finding: this is
repo-observable readiness only. It is NOT a conformity assessment, NOT
vulnerability reporting, and NOT legal advice. Absence of an item is not proof
of non-compliance, and presence is not proof of compliance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

__all__ = [
    "CraItem",
    "CraReadiness",
    "CRA_READINESS_VERSION",
    "CRA_SCOPE",
    "STATUS_PRESENT",
    "STATUS_ABSENT",
    "STATUS_NOT_APPLICABLE",
]

# The artifact schema version. Bump only on a breaking shape change so a reader
# can trust the key set at a given version.
CRA_READINESS_VERSION = 1

# The mandatory scope copy (task requirement 5). Written verbatim as the
# artifact's top-level "scope" string and into every finding's detail so no
# reader can mistake the checklist for a compliance verdict. Kept as one
# constant so both surfaces stay identical.
CRA_SCOPE = (
    "Repo-observable CRA readiness only. This enumerates repository artifacts "
    "that an EU Cyber Resilience Act technical file references, checked by "
    "presence or absence. It is NOT a conformity assessment, NOT vulnerability "
    "reporting, and NOT legal advice. Absence of an item is not proof of "
    "non-compliance, and presence is not proof of compliance."
)

# Status vocabulary. present: the artifact was observed in the repository.
# absent: it was looked for and not found (a gap; emits a finding unless the
# item is an observation). not_applicable: the check could not run (for example
# the signed-commit sample when there is no git history), never a silent drop.
STATUS_PRESENT = "present"
STATUS_ABSENT = "absent"
STATUS_NOT_APPLICABLE = "not_applicable"


@dataclass
class CraItem:
    """One checklist item: a deterministic presence/absence check with evidence.

    ``evidence`` is ``{"path": <repo-relative path or None>, "detail": <matched
    line/section or None>}`` when there is anything to point at, else ``None``
    (an explicit gap). ``cra_clause`` is a short reference string naming the
    obligation the item speaks to; it is a pointer, not a legal claim.
    ``observation`` marks the signed-commit sample as a hygiene observation
    rather than a pass/fail item, so it never emits a finding regardless of
    status. ``rank_score`` sizes the finding an absent item emits (0.0 for
    present, not_applicable, or observation items, which emit none).
    """

    id: str
    label: str
    status: str
    cra_clause: str
    evidence: Optional[dict] = None
    observation: bool = False
    rank_score: float = 0.0
    # A short remediation line carried into the finding detail (what artifact to
    # add). Empty for present items.
    remediation: str = ""

    def to_dict(self) -> dict:
        """The compact JSON shape for the cra-readiness.json items list."""
        out: dict = {
            "id": self.id,
            "label": self.label,
            "status": self.status,
            "evidence": self.evidence,
            "cra_clause": self.cra_clause,
        }
        # observation rides only when set, so the five pass/fail items stay compact.
        if self.observation:
            out["observation"] = True
        return out

    def emits_finding(self) -> bool:
        """Only absent, non-observation items surface as findings (task 4)."""
        return self.status == STATUS_ABSENT and not self.observation

    def to_finding(self) -> dict:
        """Render this absent item as a finding for the existing findings surface.

        The finding carries the CRA-clause reference and the honest scope caveat
        in its detail (task 4/5). Members and evidence are empty: an absent
        artifact has no location to point at, and the FindingsSurface renders a
        zero-member finding without a location link.
        """
        return {
            "id": f"finding:cra:{self.id}",
            "kind": "cra_readiness",
            "summary": (
                f"CRA readiness: {self.label} not found in the repository. "
                f"{self.remediation}".strip()
            ),
            "members": [],
            "evidence": [],
            "confidence": "inferred",
            "verification_status": "unverified",
            "rank_score": round(self.rank_score, 4),
            "detail": {
                "item_id": self.id,
                "status": self.status,
                "cra_clause": self.cra_clause,
                "remediation": self.remediation,
                "scope": CRA_SCOPE,
            },
        }


@dataclass
class CraReadiness:
    """The whole checklist: the ordered items plus the shared scope copy."""

    items: list[CraItem] = field(default_factory=list)

    def to_artifact(self) -> dict:
        """The versioned, byte-stable cra-readiness.json document.

        The scope string is top-level and prominent (task 5). Items keep their
        construction order (a fixed order, see checks.py), so the document is
        deterministic without a sort.
        """
        return {
            "cra_readiness_version": CRA_READINESS_VERSION,
            "kind": "solution-explorer-cra-readiness",
            "scope": CRA_SCOPE,
            "items": [it.to_dict() for it in self.items],
        }

    def findings(self) -> list[dict]:
        """The findings for the absent, non-observation items (gaps only)."""
        return [it.to_finding() for it in self.items if it.emits_finding()]
