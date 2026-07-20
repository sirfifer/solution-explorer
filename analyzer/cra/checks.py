"""Deterministic CRA-readiness checks (P10-4, Option C).

``build_cra_readiness`` runs one presence/absence check per checklist item
against the repository root and the already-collected supply_chain section, and
returns a ``CraReadiness``. Every check is a plain file-existence or text-scan
test, no clock and no network, so the artifact is byte-stable given the same
repository state (invariant I4). The one exception, the signed-commit sample, is
a git observation bounded to the recent history and reported as a hygiene
observation, never a pass/fail (task 2).

Repo-observable readiness ONLY (VISION.md No theater): each check asserts what
the repository shows and nothing more. No conformity is assessed, no
vulnerability is reported.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from .models import (
    STATUS_ABSENT,
    STATUS_NOT_APPLICABLE,
    STATUS_PRESENT,
    CraItem,
    CraReadiness,
)

__all__ = ["build_cra_readiness"]

# CRA-clause reference strings. Short pointers to the obligation each item speaks
# to, grounded in Annex I Part II (vulnerability-handling requirements) and
# Article 13; they are references, not legal claims (see CRA_SCOPE).
_CLAUSE_SECURITY_MD = "Annex I Part II(5) coordinated vulnerability disclosure policy"
_CLAUSE_CVD_CONTACT = "Annex I Part II(6) single point of contact for vulnerability reports"
_CLAUSE_SBOM = "Annex I Part II(1) SBOM covering at least the top-level dependencies"
_CLAUSE_UPDATE_CONFIG = "Annex I Part II(7) secure distribution of security updates"
_CLAUSE_SUPPORT = "Article 13(8) support period statement; Annex I Part II(8) timely security updates"
_CLAUSE_SIGNED = "Annex I Part I(2)(f) integrity protection (hygiene observation, not a CRA obligation line)"

# Candidate locations for SECURITY.md, in a fixed check order (the standard
# GitHub-recognized locations). The first that exists wins so evidence is stable.
_SECURITY_MD_CANDIDATES = ("SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md")

# Candidate security.txt locations (RFC 9116), preferred order.
_SECURITY_TXT_CANDIDATES = (".well-known/security.txt", "security.txt")

# Candidate support-policy docs when SECURITY.md carries no Supported Versions.
_SUPPORT_DOC_CANDIDATES = ("SUPPORT.md", ".github/SUPPORT.md", "docs/SUPPORT.md")

# Candidate update/dependency-management configs, fixed order.
_UPDATE_CONFIG_CANDIDATES = (
    ".github/dependabot.yml",
    ".github/dependabot.yaml",
    "renovate.json",
    "renovate.json5",
    ".renovate.json",
    ".github/renovate.json",
)

# Per-item rank for the finding an absent item emits. Chosen so a missing
# SECURITY.md and a missing SBOM surface near the top of the ranked findings
# list, above the extractor-blind-spot orphans (~12-37) and among the
# inconsistency findings (~60-90), without artificially dominating everything.
_RANK = {
    "security_md": 72.0,
    "sbom": 66.0,
    "cvd_contact": 58.0,
    "dependency_update_config": 44.0,
    "support_statement": 38.0,
}

# An email address or a URL, used to spot a concrete disclosure contact in
# SECURITY.md. Kept intentionally simple: a contact section that names a channel
# also matches via _CVD_SECTION_RE, so this only needs to catch a literal.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL_RE = re.compile(r"https?://\S+")
# A reporting/disclosure section heading or line in SECURITY.md. Any of these is
# a coordinated-disclosure channel description, which is the contact the CRA
# technical file references.
_CVD_SECTION_RE = re.compile(
    r"(report(ing)?\s+a?\s*vulnerabilit|vulnerabilit\w*\s+report|"
    r"security\s+advisor|coordinated\s+(vulnerability\s+)?disclosure|"
    r"how\s+to\s+report)",
    re.IGNORECASE,
)
# The Supported Versions heading (support/EOL statement) in SECURITY.md.
# Placeholder / template language that must never count as a real contact or
# statement (adversarial-review: TODO stubs were claimed present).
# A line that names a CONCRETE disclosure channel, not just a section heading.
# A bare "## Reporting a Vulnerability" heading with a TODO under it is a
# template; a line that names email/advisory/private-reporting is a real
# channel. Combined with the placeholder guard, this accepts a genuine
# reporting section (GitHub Security Advisory, "email the maintainer") and
# rejects a stub.
_CHANNEL_RE = re.compile(
    r"(github\s+security\s+advisor|security\s+advisor|"
    r"private\s+vulnerability\s+report|report\s+(a\s+)?vulnerabilit\w*\s+"
    r"(to|at|via|through|by)|email\s+(the|us|to|at|the\s+maintainer)|"
    r"contact\s+(us|the|:))",
    re.IGNORECASE,
)
_PLACEHOLDER_RE = re.compile(
    r"\b(TODO|TBD|FIXME|coming\s+soon|to\s+be\s+(determined|added|written)|"
    r"placeholder|describe\s+how|fill\s+in|xxx+)\b",
    re.IGNORECASE,
)
_SUPPORTED_VERSIONS_RE = re.compile(r"^\s{0,3}#{1,6}\s*supported\s+versions", re.IGNORECASE | re.MULTILINE)
# security.txt Contact field (RFC 9116).
_SECURITY_TXT_CONTACT_RE = re.compile(r"^\s*Contact\s*:\s*(\S.*)$", re.IGNORECASE | re.MULTILINE)

# How many recent commits the signed-commit observation samples.
_SIGNED_COMMIT_SAMPLE = 50


def build_cra_readiness(
    root: Path,
    *,
    supply_chain: Optional[dict] = None,
) -> CraReadiness:
    """Run every checklist check against ``root`` and return the CraReadiness.

    ``supply_chain`` is the projection's supply_chain section (the P10-1 SBOM
    summary), or None when no SBOM was emitted. Items are built in a fixed order
    so the artifact is deterministic without a sort.
    """
    root = Path(root)
    security_md = _find_first(root, _SECURITY_MD_CANDIDATES)
    items = [
        _check_security_md(security_md, root),
        _check_cvd_contact(root, security_md),
        _check_sbom(supply_chain),
        _check_update_config(root),
        _check_support_statement(root, security_md),
        _check_signed_commits(root),
    ]
    return CraReadiness(items=items)


# ---------------------------------------------------------------------------
# individual checks
# ---------------------------------------------------------------------------

def _check_security_md(security_md: Optional[str], root: Path) -> CraItem:
    # Existence alone is not enough: an empty or whitespace-only SECURITY.md is
    # not a security policy (adversarial-review over-claim). Require some real
    # content before reporting present.
    if security_md is not None and _has_content(root / security_md):
        return CraItem(
            id="security_md",
            label="Security policy (SECURITY.md)",
            status=STATUS_PRESENT,
            cra_clause=_CLAUSE_SECURITY_MD,
            evidence={"path": security_md, "detail": None},
        )
    return CraItem(
        id="security_md",
        label="Security policy (SECURITY.md)",
        status=STATUS_ABSENT,
        cra_clause=_CLAUSE_SECURITY_MD,
        evidence=None,
        rank_score=_RANK["security_md"],
        remediation="Add a SECURITY.md at the repo root, in .github/, or in docs/.",
    )


def _check_cvd_contact(root: Path, security_md: Optional[str]) -> CraItem:
    """A coordinated-disclosure contact: security.txt, or a contact in SECURITY.md."""
    # security.txt (RFC 9116) is the most explicit machine-readable contact.
    # A security.txt counts ONLY when it carries a real Contact field. RFC 9116
    # makes Contact mandatory; a contactless security.txt gives no disclosure
    # contact, so it must not report present or suppress the gap finding
    # (adversarial-review over-claim). Falls through to SECURITY.md / absent.
    txt = _find_first(root, _SECURITY_TXT_CANDIDATES)
    if txt is not None:
        contact_line = _first_match_line(root / txt, _SECURITY_TXT_CONTACT_RE)
        if contact_line is not None:
            return CraItem(
                id="cvd_contact",
                label="Vulnerability disclosure contact",
                status=STATUS_PRESENT,
                cra_clause=_CLAUSE_CVD_CONTACT,
                evidence={"path": txt, "detail": contact_line},
            )
    # A contact named in SECURITY.md: a literal email/URL, or a reporting section.
    if security_md is not None:
        text = _read_text(root / security_md)
        line = _first_contact_line(text)
        if line is not None:
            return CraItem(
                id="cvd_contact",
                label="Vulnerability disclosure contact",
                status=STATUS_PRESENT,
                cra_clause=_CLAUSE_CVD_CONTACT,
                evidence={"path": security_md, "detail": line},
            )
    return CraItem(
        id="cvd_contact",
        label="Vulnerability disclosure contact",
        status=STATUS_ABSENT,
        cra_clause=_CLAUSE_CVD_CONTACT,
        evidence=None,
        rank_score=_RANK["cvd_contact"],
        remediation=(
            "Add a .well-known/security.txt with a Contact field, or a reporting "
            "contact in SECURITY.md."
        ),
    )


def _check_sbom(supply_chain: Optional[dict]) -> CraItem:
    """SBOM presence read from the P10-1 supply_chain section (task 2)."""
    if supply_chain is None:
        # No dependency manifests were found, so no sbom.json was emitted. Honest
        # gap, not a silent pass.
        return CraItem(
            id="sbom",
            label="Software bill of materials (sbom.json)",
            status=STATUS_ABSENT,
            cra_clause=_CLAUSE_SBOM,
            evidence=None,
            rank_score=_RANK["sbom"],
            remediation=(
                "No dependency manifests were found, so no SBOM was emitted. Ship "
                "a manifest (package.json, pyproject.toml, go.mod, ...) so a "
                "CycloneDX sbom.json can be produced."
            ),
        )
    count = 0
    counts = supply_chain.get("counts")
    if isinstance(counts, dict):
        count = int(counts.get("dependencies", 0) or 0)
    endpoint = supply_chain.get("sbom_endpoint", "sbom.json")
    if count == 0:
        # The SBOM is emitted but carries zero shipping dependencies. Report that
        # honestly rather than implying a populated bill of materials (task 2).
        detail = (
            "sbom.json emitted with 0 shipping dependencies (no shipping "
            "dependency manifest resolved to a component)."
        )
    else:
        detail = f"sbom.json emitted with {count} shipping dependency component(s)."
    return CraItem(
        id="sbom",
        label="Software bill of materials (sbom.json)",
        status=STATUS_PRESENT,
        cra_clause=_CLAUSE_SBOM,
        evidence={"path": endpoint, "detail": detail},
    )


def _check_update_config(root: Path) -> CraItem:
    found = _find_first(root, _UPDATE_CONFIG_CANDIDATES)
    if found is not None:
        return CraItem(
            id="dependency_update_config",
            label="Dependency update configuration",
            status=STATUS_PRESENT,
            cra_clause=_CLAUSE_UPDATE_CONFIG,
            evidence={"path": found, "detail": None},
        )
    return CraItem(
        id="dependency_update_config",
        label="Dependency update configuration",
        status=STATUS_ABSENT,
        cra_clause=_CLAUSE_UPDATE_CONFIG,
        evidence=None,
        rank_score=_RANK["dependency_update_config"],
        remediation=(
            "Add .github/dependabot.yml or renovate.json so dependency updates "
            "are managed."
        ),
    )


def _check_support_statement(root: Path, security_md: Optional[str]) -> CraItem:
    """A support/EOL statement: a Supported Versions section, or a support doc."""
    if security_md is not None:
        text = _read_text(root / security_md)
        m = _SUPPORTED_VERSIONS_RE.search(text)
        if m is not None:
            line = text[m.start():m.end()].strip()
            return CraItem(
                id="support_statement",
                label="Support or end-of-life statement",
                status=STATUS_PRESENT,
                cra_clause=_CLAUSE_SUPPORT,
                evidence={"path": security_md, "detail": line},
            )
    doc = _find_first(root, _SUPPORT_DOC_CANDIDATES)
    if doc is not None and _has_content(root / doc):
        return CraItem(
            id="support_statement",
            label="Support or end-of-life statement",
            status=STATUS_PRESENT,
            cra_clause=_CLAUSE_SUPPORT,
            evidence={"path": doc, "detail": None},
        )
    return CraItem(
        id="support_statement",
        label="Support or end-of-life statement",
        status=STATUS_ABSENT,
        cra_clause=_CLAUSE_SUPPORT,
        evidence=None,
        rank_score=_RANK["support_statement"],
        remediation=(
            "Add a Supported Versions section to SECURITY.md or a SUPPORT.md "
            "stating the support/EOL period."
        ),
    )


def _check_signed_commits(root: Path) -> CraItem:
    """Signed-commit sample over recent history: a hygiene OBSERVATION (task 2).

    Reported as an observation, never a pass/fail, so it emits no finding
    regardless of status. not_applicable when git is unavailable or the repo has
    no commits (never a silent drop).
    """
    statuses = _git_signature_statuses(root, _SIGNED_COMMIT_SAMPLE)
    if statuses is None:
        return CraItem(
            id="signed_commits",
            label="Signed-commit sample (recent history)",
            status=STATUS_NOT_APPLICABLE,
            cra_clause=_CLAUSE_SIGNED,
            evidence={"path": None, "detail": "No git history available to sample."},
            observation=True,
        )
    total = len(statuses)
    # %G? codes: N = no signature, B = bad signature; anything else carries a
    # signature. "Signed" counts a present signature, not signature validity.
    signed = sum(1 for s in statuses if s not in ("N", "B"))
    status = STATUS_PRESENT if signed > 0 else STATUS_ABSENT
    detail = (
        f"{signed} of the last {total} commit(s) carry a signature "
        f"(git log --format=%G?). Hygiene observation, not a pass/fail."
    )
    return CraItem(
        id="signed_commits",
        label="Signed-commit sample (recent history)",
        status=status,
        cra_clause=_CLAUSE_SIGNED,
        evidence={"path": None, "detail": detail},
        observation=True,
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _find_first(root: Path, candidates) -> Optional[str]:
    """The first candidate (repo-relative) that exists as a file, else None."""
    for rel in candidates:
        if (root / rel).is_file():
            return rel
    return None


def _has_content(path: Path) -> bool:
    """True when a file carries more than trivial whitespace (adversarial-review:
    an empty SECURITY.md or SUPPORT.md must not report present). A low bar on
    purpose: presence of a real policy is judged by a human, but a zero-content
    file is objectively not one.
    """
    try:
        return len(_read_text(path).strip()) >= 16
    except OSError:
        return False


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _first_match_line(path: Path, pattern: re.Pattern) -> Optional[str]:
    """The captured group (or whole match) of the first line matching pattern."""
    text = _read_text(path)
    m = pattern.search(text)
    if m is None:
        return None
    return (m.group(1) if m.groups() else m.group(0)).strip()


def _first_contact_line(text: str) -> Optional[str]:
    """The first SECURITY.md line naming a contact: email, URL, or report section."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _PLACEHOLDER_RE.search(line):
            # A template stub (TODO, TBD, coming soon, "describe how to report")
            # is not a real contact (adversarial-review over-claim): skip it so
            # it neither reports present nor suppresses the gap finding.
            continue
        # A concrete channel is an actual email or URL, or a real
        # reporting/disclosure section that named a channel (a GitHub Security
        # Advisory section is a legitimate coordinated-disclosure channel with
        # no inline email). The placeholder guard above already rejected the
        # template forms of the section language.
        if _EMAIL_RE.search(line) or _URL_RE.search(line) or _CHANNEL_RE.search(line):
            # Collapse a heading marker so the evidence line reads cleanly.
            return line.lstrip("#").strip()
    return None


def _git_signature_statuses(root: Path, limit: int) -> Optional[list[str]]:
    """The %G? code for each of the last ``limit`` commits, or None on failure.

    Bounded and defensive: a missing git binary, a non-repository root, or an
    empty history returns None (the observation is not_applicable), never raises.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "log", "--no-show-signature",
             "--format=%G?", f"-n{int(limit)}"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    codes = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    if not codes:
        return None
    return codes
