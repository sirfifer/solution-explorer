"""CRA readiness checklist and findings (P10-4, Option C).

These tests drive the real checks and the real projection pipeline against
constructed repositories and committed fixtures (no mocks). They encode the
card's accept criteria:

  - a repo WITH the artifacts reports every item present; a repo WITHOUT reports
    them absent and emits one finding per absent pass/fail item;
  - each check's presence and absence in isolation, with evidence pointers;
  - the SBOM-present item reads the real emitted supply_chain section shape;
  - the cra-readiness.json artifact is emitted in both split and monolith modes,
    with the endpoint and the "is this repo CRA-ready" walk order in ai.json;
  - the artifact is versioned, byte-stable (determinism), and carries the
    mandatory top-level scope string;
  - the self repo end to end: SECURITY.md and sbom.json report present with
    evidence, the update-config is honestly absent.
"""

from __future__ import annotations

import json
from pathlib import Path

from analyzer.cra import (
    CRA_READINESS_VERSION,
    CRA_SCOPE,
    build_cra_readiness,
)
from analyzer.cra.models import (
    STATUS_ABSENT,
    STATUS_NOT_APPLICABLE,
    STATUS_PRESENT,
)
from analyzer.derive import derive_all
from analyzer.extract import extract_repo
from analyzer.project.cra_emit import emit_cra_readiness
from analyzer.project.pipeline import project_monolith, project_split
from analyzer.sbom import collect_supply_chain
from analyzer.store import FactStore

FIXTURES = Path(__file__).parent / "fixtures"
POLYGLOT = FIXTURES / "polyglot"
REPO_ROOT = Path(__file__).resolve().parent.parent

FIXED_TS = "2020-01-01T00:00:00Z"

# A supply_chain section with a populated dependency count, matching the shape
# emitted by SupplyChain.to_section (only the keys the SBOM check reads).
_SUPPLY = {"sbom_endpoint": "sbom.json", "counts": {"dependencies": 3}}


def _items_by_id(readiness):
    return {it.id: it for it in readiness.items}


# ---------------------------------------------------------------------------
# A repo WITH every artifact present
# ---------------------------------------------------------------------------

def _make_ready_repo(root: Path) -> None:
    """Create a repository carrying every checklist artifact."""
    (root / "SECURITY.md").write_text(
        "# Security Policy\n\n"
        "## Supported Versions\n\n"
        "Only the latest release is supported.\n\n"
        "## Reporting a Vulnerability\n\n"
        "Email security@example.com to report a vulnerability.\n",
        encoding="utf-8",
    )
    (root / ".github").mkdir(parents=True, exist_ok=True)
    (root / ".github" / "dependabot.yml").write_text(
        "version: 2\nupdates:\n  - package-ecosystem: npm\n", encoding="utf-8"
    )


def test_all_present_repo_reports_every_item_present_no_findings(tmp_path):
    _make_ready_repo(tmp_path)
    readiness = build_cra_readiness(tmp_path, supply_chain=_SUPPLY)
    items = _items_by_id(readiness)

    assert items["security_md"].status == STATUS_PRESENT
    assert items["cvd_contact"].status == STATUS_PRESENT
    assert items["sbom"].status == STATUS_PRESENT
    assert items["dependency_update_config"].status == STATUS_PRESENT
    assert items["support_statement"].status == STATUS_PRESENT
    # signed_commits is an observation; tmp_path is not a git repo, so N/A.
    assert items["signed_commits"].status == STATUS_NOT_APPLICABLE
    assert items["signed_commits"].observation is True

    # Every pass/fail item present, so no gap findings are emitted.
    assert readiness.findings() == []


def test_all_present_evidence_points_at_the_real_paths(tmp_path):
    _make_ready_repo(tmp_path)
    items = _items_by_id(build_cra_readiness(tmp_path, supply_chain=_SUPPLY))
    assert items["security_md"].evidence["path"] == "SECURITY.md"
    assert items["cvd_contact"].evidence["path"] == "SECURITY.md"
    assert items["dependency_update_config"].evidence["path"] == ".github/dependabot.yml"
    assert items["support_statement"].evidence["path"] == "SECURITY.md"
    assert "Supported Versions" in items["support_statement"].evidence["detail"]


# ---------------------------------------------------------------------------
# A repo WITHOUT any artifact
# ---------------------------------------------------------------------------

def test_all_absent_repo_reports_absent_and_emits_findings(tmp_path):
    (tmp_path / "README.md").write_text("# nothing here", encoding="utf-8")
    # No manifests either, so no SBOM section is available.
    readiness = build_cra_readiness(tmp_path, supply_chain=None)
    items = _items_by_id(readiness)

    for iid in (
        "security_md", "cvd_contact", "sbom",
        "dependency_update_config", "support_statement",
    ):
        assert items[iid].status == STATUS_ABSENT, iid
        assert items[iid].evidence is None, iid

    # signed_commits stays an observation, never a finding.
    assert items["signed_commits"].status == STATUS_NOT_APPLICABLE

    findings = readiness.findings()
    finding_items = {f["detail"]["item_id"] for f in findings}
    assert finding_items == {
        "security_md", "cvd_contact", "sbom",
        "dependency_update_config", "support_statement",
    }
    # The observation never emits a finding, even when it is not_applicable.
    assert "signed_commits" not in finding_items


def test_absent_findings_carry_kind_clause_and_scope(tmp_path):
    (tmp_path / "README.md").write_text("# empty", encoding="utf-8")
    findings = build_cra_readiness(tmp_path, supply_chain=None).findings()
    for f in findings:
        assert f["kind"] == "cra_readiness"
        assert f["verification_status"] == "unverified"
        assert f["detail"]["cra_clause"]           # non-empty clause reference
        assert f["detail"]["scope"] == CRA_SCOPE    # scope caveat in every finding
    # A missing SECURITY.md and a missing SBOM outrank the softer gaps (task 4).
    by_item = {f["detail"]["item_id"]: f["rank_score"] for f in findings}
    assert by_item["security_md"] > by_item["support_statement"]
    assert by_item["sbom"] > by_item["dependency_update_config"]


# ---------------------------------------------------------------------------
# Each check in isolation
# ---------------------------------------------------------------------------

def test_security_md_found_in_github_dir(tmp_path):
    gh = tmp_path / ".github"
    gh.mkdir()
    (gh / "SECURITY.md").write_text(
        "# Security Policy\n\nReport vulnerabilities to security@example.com.\n",
        encoding="utf-8",
    )
    items = _items_by_id(build_cra_readiness(tmp_path))
    assert items["security_md"].status == STATUS_PRESENT
    assert items["security_md"].evidence["path"] == ".github/SECURITY.md"


def test_cvd_contact_from_security_txt(tmp_path):
    wk = tmp_path / ".well-known"
    wk.mkdir()
    (wk / "security.txt").write_text(
        "Contact: mailto:security@example.com\nExpires: 2030-01-01T00:00:00Z\n",
        encoding="utf-8",
    )
    items = _items_by_id(build_cra_readiness(tmp_path))
    cvd = items["cvd_contact"]
    assert cvd.status == STATUS_PRESENT
    assert cvd.evidence["path"] == ".well-known/security.txt"
    assert "security@example.com" in cvd.evidence["detail"]


def test_cvd_contact_from_security_md_email(tmp_path):
    # A SECURITY.md with a literal email but NO reporting heading still counts.
    (tmp_path / "SECURITY.md").write_text(
        "# Security\n\nWrite to team@example.org for anything.\n", encoding="utf-8"
    )
    items = _items_by_id(build_cra_readiness(tmp_path))
    assert items["cvd_contact"].status == STATUS_PRESENT
    assert "team@example.org" in items["cvd_contact"].evidence["detail"]


def test_cvd_contact_absent_when_security_md_has_no_contact(tmp_path):
    # A SECURITY.md that describes policy but names no contact or report channel.
    (tmp_path / "SECURITY.md").write_text(
        "# Security\n\nWe care about security and patch things.\n", encoding="utf-8"
    )
    items = _items_by_id(build_cra_readiness(tmp_path))
    assert items["security_md"].status == STATUS_PRESENT
    assert items["cvd_contact"].status == STATUS_ABSENT


def test_update_config_renovate(tmp_path):
    (tmp_path / "renovate.json").write_text("{}", encoding="utf-8")
    items = _items_by_id(build_cra_readiness(tmp_path))
    assert items["dependency_update_config"].status == STATUS_PRESENT
    assert items["dependency_update_config"].evidence["path"] == "renovate.json"


def test_support_statement_from_support_doc(tmp_path):
    # No SECURITY.md, but a SUPPORT.md satisfies the support-statement item.
    (tmp_path / "SUPPORT.md").write_text("# Support\n\nWe support the latest.\n", encoding="utf-8")
    items = _items_by_id(build_cra_readiness(tmp_path))
    assert items["support_statement"].status == STATUS_PRESENT
    assert items["support_statement"].evidence["path"] == "SUPPORT.md"


def test_signed_commits_observation_in_real_git_repo():
    # The self repo IS a git repo, so the sample runs and the item is present or
    # absent, always an observation, never a finding.
    items = _items_by_id(build_cra_readiness(REPO_ROOT, supply_chain=_SUPPLY))
    sc = items["signed_commits"]
    assert sc.observation is True
    assert sc.status in (STATUS_PRESENT, STATUS_ABSENT)
    assert "commit" in sc.evidence["detail"]
    assert sc.emits_finding() is False


# ---------------------------------------------------------------------------
# SBOM-present detection reads the real emitted supply_chain shape
# ---------------------------------------------------------------------------

def test_sbom_item_reads_real_supply_chain_section(tmp_path):
    _make_ready_repo(tmp_path)
    section = collect_supply_chain(POLYGLOT).to_section()
    items = _items_by_id(build_cra_readiness(tmp_path, supply_chain=section))
    sbom = items["sbom"]
    assert sbom.status == STATUS_PRESENT
    assert sbom.evidence["path"] == "sbom.json"
    assert str(section["counts"]["dependencies"]) in sbom.evidence["detail"]


def test_sbom_item_zero_dependencies_is_honest(tmp_path):
    section = {"sbom_endpoint": "sbom.json", "counts": {"dependencies": 0}}
    items = _items_by_id(build_cra_readiness(tmp_path, supply_chain=section))
    sbom = items["sbom"]
    assert sbom.status == STATUS_PRESENT
    assert "0 shipping dependencies" in sbom.evidence["detail"]
    # A present item never emits a finding, even at zero dependencies.
    assert sbom.emits_finding() is False


# ---------------------------------------------------------------------------
# Artifact shape, scope, and determinism
# ---------------------------------------------------------------------------

def test_artifact_is_versioned_and_carries_scope(tmp_path):
    _make_ready_repo(tmp_path)
    art = build_cra_readiness(tmp_path, supply_chain=_SUPPLY).to_artifact()
    assert art["cra_readiness_version"] == CRA_READINESS_VERSION
    assert art["scope"] == CRA_SCOPE
    assert "NOT a conformity assessment" in art["scope"]
    assert [it["id"] for it in art["items"]] == [
        "security_md", "cvd_contact", "sbom",
        "dependency_update_config", "support_statement", "signed_commits",
    ]


def test_artifact_is_byte_stable(tmp_path):
    _make_ready_repo(tmp_path)
    a = json.dumps(build_cra_readiness(tmp_path, supply_chain=_SUPPLY).to_artifact(), sort_keys=True)
    b = json.dumps(build_cra_readiness(tmp_path, supply_chain=_SUPPLY).to_artifact(), sort_keys=True)
    assert a == b


def test_emit_cra_readiness_is_none_without_root(tmp_path):
    assert emit_cra_readiness(tmp_path, root=None) is None


# ---------------------------------------------------------------------------
# Projection emission (split and monolith) against a real store
# ---------------------------------------------------------------------------

def _project(root, tmp_path, split):
    store = FactStore(":memory:")
    extract_repo(root, store)
    _, arch = derive_all(store, root.name, root_path=str(root))
    if split:
        out = tmp_path / "arch"
        result = project_split(
            arch, out, store=store, root=root,
            generated_at=FIXED_TS, analyzer_version="test",
        )
        store.close()
        return out, result
    out = tmp_path / "architecture.json"
    result = project_monolith(
        arch, out, store=store, root=root,
        generated_at=FIXED_TS, analyzer_version="test",
    )
    store.close()
    return out, result


def test_projection_split_emits_artifact_endpoint_and_findings(tmp_path):
    out, result = _project(POLYGLOT, tmp_path, split=True)
    cra_path = out / "cra-readiness.json"
    assert cra_path.is_file()
    assert result.cra_path == cra_path

    art = json.loads(cra_path.read_text())
    assert art["cra_readiness_version"] == CRA_READINESS_VERSION
    assert art["scope"] == CRA_SCOPE

    # POLYGLOT carries manifests (SBOM present) but no SECURITY.md/dependabot, so
    # the gaps ride in the manifest findings as cra_readiness findings.
    manifest = json.loads((out / "manifest.json").read_text())
    cra_findings = [f for f in manifest["findings"] if f["kind"] == "cra_readiness"]
    kinds = {f["detail"]["item_id"] for f in cra_findings}
    assert "security_md" in kinds
    assert "sbom" not in kinds        # SBOM is present in POLYGLOT: no gap finding

    ai = json.loads((out / "ai.json").read_text())
    cra_endpoints = [e for e in ai["endpoints"] if e["path"] == "cra-readiness.json"]
    assert len(cra_endpoints) == 1
    questions = [w["question"] for w in ai["walk_orders"]]
    assert "is this repo CRA-ready" in questions
    assert "cra-readiness.json" in (out / "llms.txt").read_text()


def test_projection_monolith_emits_artifact_and_endpoint(tmp_path):
    out, result = _project(POLYGLOT, tmp_path, split=False)
    cra_path = out.parent / "cra-readiness.json"
    assert cra_path.is_file()
    assert result.cra_path == cra_path

    mono = json.loads(out.read_text())
    assert any(f["kind"] == "cra_readiness" for f in mono["findings"])

    ai = json.loads((out.parent / "ai.json").read_text())
    assert any(e["path"] == "cra-readiness.json" for e in ai["endpoints"])


def test_projection_artifact_is_byte_stable(tmp_path):
    out1, _ = _project(POLYGLOT, tmp_path / "a", split=True)
    out2, _ = _project(POLYGLOT, tmp_path / "b", split=True)
    assert (out1 / "cra-readiness.json").read_bytes() == (out2 / "cra-readiness.json").read_bytes()


# ---------------------------------------------------------------------------
# Self repository, end to end
# ---------------------------------------------------------------------------

def test_self_repo_reports_security_md_and_sbom_present():
    # The self repo HAS a SECURITY.md and (with manifests) a real SBOM section.
    section = collect_supply_chain(REPO_ROOT).to_section()
    items = _items_by_id(build_cra_readiness(REPO_ROOT, supply_chain=section))

    assert items["security_md"].status == STATUS_PRESENT
    assert items["security_md"].evidence["path"] == "SECURITY.md"
    assert items["sbom"].status == STATUS_PRESENT
    assert items["support_statement"].status == STATUS_PRESENT  # Supported Versions
    assert items["cvd_contact"].status == STATUS_PRESENT

    # Honest gap: the self repo ships no dependabot/renovate config today.
    assert items["dependency_update_config"].status == STATUS_ABSENT
    gap_items = {f["detail"]["item_id"] for f in build_cra_readiness(REPO_ROOT, supply_chain=section).findings()}
    assert "dependency_update_config" in gap_items

# ---------------------------------------------------------------------------
# Detection-honesty negative fixtures (adversarial-review findings 1-3, 5):
# an item must NOT report present on evidence that provides no real substance,
# and the gap finding must not be suppressed.
# ---------------------------------------------------------------------------


def test_contactless_security_txt_does_not_over_claim_cvd(tmp_path):
    (tmp_path / ".well-known").mkdir()
    (tmp_path / ".well-known" / "security.txt").write_text(
        "Expires: 2027-01-01T00:00:00Z\nEncryption: https://example.com/pgp\n"
    )
    readiness = build_cra_readiness(tmp_path, supply_chain=None)
    items = _items_by_id(readiness)
    assert items["cvd_contact"].status == STATUS_ABSENT, (
        "a security.txt with no Contact field is not a disclosure contact"
    )
    gaps = {f["detail"]["item_id"] for f in readiness.findings()}
    assert "cvd_contact" in gaps


def test_template_security_md_does_not_over_claim_cvd(tmp_path):
    (tmp_path / "SECURITY.md").write_text(
        "# Security\n\n## Reporting a vulnerability\n\nTODO: describe how to report.\n"
    )
    items = _items_by_id(build_cra_readiness(tmp_path, supply_chain=None))
    assert items["cvd_contact"].status == STATUS_ABSENT, (
        "a TODO template line is not a real contact"
    )


def test_real_contact_in_security_md_still_reports_present(tmp_path):
    (tmp_path / "SECURITY.md").write_text(
        "# Security\n\nReport vulnerabilities to security@example.com.\n"
    )
    items = _items_by_id(build_cra_readiness(tmp_path, supply_chain=None))
    assert items["cvd_contact"].status == STATUS_PRESENT
    assert "security@example.com" in (items["cvd_contact"].evidence or {}).get("detail", "")


def test_empty_security_md_is_not_a_policy(tmp_path):
    (tmp_path / "SECURITY.md").write_text("   \n\n")
    items = _items_by_id(build_cra_readiness(tmp_path, supply_chain=None))
    assert items["security_md"].status == STATUS_ABSENT, (
        "an empty SECURITY.md is not a security policy"
    )


def test_empty_support_doc_is_not_a_statement(tmp_path):
    (tmp_path / "SUPPORT.md").write_text("\n")
    items = _items_by_id(build_cra_readiness(tmp_path, supply_chain=None))
    assert items["support_statement"].status == STATUS_ABSENT
