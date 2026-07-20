"""SARIF 2.1.0 export (A5).

Two layers, matching the repo's own convention (test the real pipeline, not a
reimplementation of it): a schema-validation suite over hand-built finding
fixtures covering every finding kind and every location-fallback path
(analyzer/project/sarif.py's own contract), plus an end-to-end test that
drives the real extract -> derive -> project -> ``--sarif`` CLI path against a
tiny repo that genuinely produces an ``unreferenced`` finding, and validates
that output against the same schema.

Schema validation uses the committed OASIS SARIF 2.1.0 JSON Schema fixture
(tests/fixtures/sarif/sarif-schema-2.1.0.json, fetched from
https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/
sarif-schema-2.1.0.json) so the test is hermetic and does not need network
access.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import jsonschema

from analyzer.derive import derive_all
from analyzer.extract import extract_repo
from analyzer.project.sarif import build_sarif, write_sarif
from analyzer.store import FactStore

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA_PATH = FIXTURES / "sarif" / "sarif-schema-2.1.0.json"
REPO_ROOT = Path(__file__).resolve().parent.parent

_SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate(doc: dict) -> None:
    jsonschema.validate(instance=doc, schema=_SCHEMA, format_checker=jsonschema.FormatChecker())


# ---------------------------------------------------------------------------
# Hand-built fixtures covering every finding kind (LENS-DESIGN section 9,
# P7-4 intent-violation, P10-4 cra_readiness). Shapes copied verbatim from
# their producers: analyzer/derive/correlations.py, analyzer/enrich/passes.py,
# analyzer/cra/models.py.
# ---------------------------------------------------------------------------

_COMPONENTS = [
    {
        "id": "comp:alpha",
        "name": "alpha",
        "files": ["alpha/service.py", "alpha/extra.py"],
        "children": [],
    },
    {
        "id": "comp:beta",
        "name": "beta",
        "files": ["beta/service.py"],
        "children": [],
    },
]

_DUPLICATION = {
    "id": "finding:duplication:abcd1234",
    "kind": "duplication",
    "summary": "renamed clone across 2 fragments in 2 components",
    "members": [
        {
            "kind": "fragment", "id": "alpha/service.py:10",
            "file": "alpha/service.py", "line_start": 10, "line_end": 20,
            "symbol": "process_alpha", "component_id": "comp:alpha",
        },
        {
            "kind": "fragment", "id": "beta/service.py:5",
            "file": "beta/service.py", "line_start": 5, "line_end": 15,
            "symbol": "process_beta", "component_id": "comp:beta",
        },
    ],
    "evidence": [
        {"file": "alpha/service.py", "line": 10, "end_line": 20, "symbol": "process_alpha"},
        {"file": "beta/service.py", "line": 5, "end_line": 15, "symbol": "process_beta"},
    ],
    "confidence": "inferred",
    "verification_status": "unverified",
    "rank_score": 138.5,
    "detail": {"clone_class": "renamed"},
}

_INCONSISTENCY = {
    "id": "finding:inconsistency:logging-deadbeef",
    "kind": "inconsistency",
    "summary": "logging concern uses 2 distinct implementations: loguru, structlog",
    "members": [
        {"kind": "component", "id": "comp:alpha", "component_id": "comp:alpha", "markers": ["structlog"]},
        {"kind": "component", "id": "comp:beta", "component_id": "comp:beta", "markers": ["loguru"]},
    ],
    "evidence": [
        {"component_id": "comp:alpha", "libraries": ["structlog"], "files": ["alpha/service.py"]},
        {"component_id": "comp:beta", "libraries": ["loguru"], "files": ["beta/service.py"]},
    ],
    "confidence": "inferred",
    "verification_status": "unverified",
    "rank_score": 83.0,
    "detail": {"concern_id": "concern:logging", "libraries": ["loguru", "structlog"]},
}

_UNREFERENCED = {
    "id": "finding:unreferenced:comp:alpha",
    "kind": "unreferenced",
    "summary": "no reference to component 'alpha' was detected by the current extractors",
    "members": [
        {"kind": "component", "id": "comp:alpha", "component_id": "comp:alpha",
         "file": None, "line_start": None, "line_end": None},
    ],
    "evidence": [
        {"component_id": "comp:alpha", "path": "alpha", "files": ["alpha/service.py"],
         "type": "module", "symbols": 3, "churn_commits": 1,
         "reference_extractor": "mature"},
    ],
    "confidence": "inferred",
    "verification_status": "unverified",
    "rank_score": 12.0,
    "detail": {"lines": 40, "symbols": 3},
}

_INTENT_VIOLATION = {
    "id": "finding:intent-violation:abc123",
    "kind": "intent-violation",
    "summary": "The audio pipeline reads from the network directly, violating the on-device intent.",
    "members": [
        {"kind": "component", "id": "comp:beta", "component_id": "comp:beta", "why": "opens a socket"},
    ],
    "evidence": [
        {"intent": "All audio processing runs on-device."},
        {"reason": "beta opens a network socket in its audio path."},
    ],
    "confidence": "medium",
    "verification_status": "unverified",
    "rank_score": 51.0,
    "intent_id": "intent:on-device-audio",
}

_CRA_READINESS = {
    "id": "finding:cra:security-md",
    "kind": "cra_readiness",
    "summary": "CRA readiness: SECURITY.md not found in the repository. Add a SECURITY.md.",
    "members": [],
    "evidence": [],
    "confidence": "inferred",
    "verification_status": "unverified",
    "rank_score": 40.0,
    "detail": {"item_id": "security-md", "status": "absent", "cra_clause": "Art. 13"},
}

_REFUTED_UNKNOWN_KIND = {
    "id": "finding:future-kind:zzz",
    "kind": "a-kind-that-does-not-exist-yet",
    "summary": "Refuted by a later AI verification pass.",
    "members": [],
    "evidence": [],
    "confidence": "inferred",
    "verification_status": "refuted",
    "verdict": {"reason": "Investigated: this is intentional, not a defect."},
    "rank_score": 5.0,
    "detail": {},
}

_ALL_FINDINGS = [
    _DUPLICATION, _INCONSISTENCY, _UNREFERENCED, _INTENT_VIOLATION,
    _CRA_READINESS, _REFUTED_UNKNOWN_KIND,
]


def _arch(findings=_ALL_FINDINGS):
    return {"components": _COMPONENTS, "findings": findings}


# ---------------------------------------------------------------------------
# Schema validity
# ---------------------------------------------------------------------------

def test_full_finding_set_is_schema_valid():
    doc = build_sarif(_arch())
    _validate(doc)


def test_empty_findings_is_schema_valid():
    doc = build_sarif({"components": [], "findings": []})
    _validate(doc)
    assert doc["runs"][0]["results"] == []
    assert doc["runs"][0]["tool"]["driver"]["rules"] == []


def test_missing_findings_key_is_schema_valid():
    doc = build_sarif({})
    _validate(doc)


# ---------------------------------------------------------------------------
# Mapping correctness
# ---------------------------------------------------------------------------

def test_top_level_shape():
    doc = build_sarif(_arch())
    assert doc["version"] == "2.1.0"
    assert doc["$schema"]
    driver = doc["runs"][0]["tool"]["driver"]
    assert driver["name"] == "solution-explorer"
    assert driver["version"]


def test_one_rule_per_distinct_kind_including_unknown():
    doc = build_sarif(_arch())
    rules = doc["runs"][0]["tool"]["driver"]["rules"]
    rule_ids = {r["id"] for r in rules}
    assert rule_ids == {
        "duplication", "inconsistency", "unreferenced", "intent-violation",
        "cra_readiness", "a-kind-that-does-not-exist-yet",
    }
    # Every ruleIndex on a result actually points at that rule's position.
    results = doc["runs"][0]["results"]
    by_index = {i: r["id"] for i, r in enumerate(rules)}
    for res in results:
        assert by_index[res["ruleIndex"]] == res["ruleId"]


def test_duplication_uses_member_file_and_line():
    doc = build_sarif(_arch([_DUPLICATION]))
    result = doc["runs"][0]["results"][0]
    locs = result["locations"]
    assert len(locs) == 2
    uris = {loc["physicalLocation"]["artifactLocation"]["uri"] for loc in locs}
    assert uris == {"alpha/service.py", "beta/service.py"}
    first = locs[0]["physicalLocation"]
    assert first["region"]["startLine"] == 10
    assert first["region"]["endLine"] == 20
    assert result["level"] == "warning"


def test_unreferenced_falls_back_to_evidence_path():
    doc = build_sarif(_arch([_UNREFERENCED]))
    result = doc["runs"][0]["results"][0]
    loc = result["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "alpha"
    assert loc["region"]["startLine"] == 1
    assert result["level"] == "note"


def test_inconsistency_falls_back_to_evidence_files_list():
    doc = build_sarif(_arch([_INCONSISTENCY]))
    result = doc["runs"][0]["results"][0]
    uris = {loc["physicalLocation"]["artifactLocation"]["uri"] for loc in result["locations"]}
    assert uris == {"alpha/service.py", "beta/service.py"}


def test_intent_violation_resolves_component_to_its_file():
    doc = build_sarif(_arch([_INTENT_VIOLATION]))
    result = doc["runs"][0]["results"][0]
    loc = result["locations"][0]["physicalLocation"]
    # comp:beta's first file, resolved from the component tree.
    assert loc["artifactLocation"]["uri"] == "beta/service.py"
    assert result["level"] == "error"


def test_cra_readiness_falls_back_to_readme():
    # A location-less finding anchors at a real committed file (README.md), not
    # at the directory marker ".", which GitHub code scanning may drop.
    doc = build_sarif(_arch([_CRA_READINESS]))
    result = doc["runs"][0]["results"][0]
    loc = result["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "README.md"
    assert loc["region"]["startLine"] == 1


def test_refuted_finding_carries_a_suppression_and_unknown_kind_gets_default_rule():
    doc = build_sarif(_arch([_REFUTED_UNKNOWN_KIND]))
    result = doc["runs"][0]["results"][0]
    assert result["suppressions"] == [
        {"kind": "external", "justification": "Investigated: this is intentional, not a defect."}
    ]
    rule = doc["runs"][0]["tool"]["driver"]["rules"][0]
    assert rule["id"] == "a-kind-that-does-not-exist-yet"
    assert rule["name"] == "Finding"  # the default rule, not a KeyError


def test_verification_status_and_rank_score_ride_in_properties():
    doc = build_sarif(_arch([_DUPLICATION]))
    props = doc["runs"][0]["results"][0]["properties"]
    assert props["verificationStatus"] == "unverified"
    assert props["rankScore"] == 138.5
    assert props["findingId"] == "finding:duplication:abcd1234"


def test_partial_fingerprint_is_the_findings_own_content_derived_id():
    doc = build_sarif(_arch([_UNREFERENCED]))
    fp = doc["runs"][0]["results"][0]["partialFingerprints"]
    assert fp["solutionExplorerFindingId/v1"] == "finding:unreferenced:comp:alpha"


def test_finding_without_id_omits_partial_fingerprints():
    # An id-less finding must NOT emit partialFingerprints: {"...": ""}. Sending
    # an empty fingerprint would collapse every id-less result onto one shared
    # fingerprint; omitting the key lets GitHub compute its own. The result must
    # still be schema-valid and carry a location.
    no_id = dict(_CRA_READINESS)
    no_id.pop("id")
    doc = build_sarif(_arch([no_id]))
    _validate(doc)
    result = doc["runs"][0]["results"][0]
    assert "partialFingerprints" not in result
    assert result["properties"]["findingId"] is None
    assert result["locations"], "an id-less finding must still carry a location"


def test_write_sarif_writes_valid_json_to_path(tmp_path):
    out = tmp_path / "nested" / "out.sarif"
    written = write_sarif(_arch(), out)
    assert written == out
    doc = json.loads(out.read_text(encoding="utf-8"))
    _validate(doc)


# ---------------------------------------------------------------------------
# End-to-end: real extraction + derivation produces an unreferenced finding,
# and the CLI's --sarif flag turns it into a schema-valid SARIF file.
# ---------------------------------------------------------------------------

_LIVE_MAIN = "def main():\n    return call_helper()\n\ndef call_helper():\n    return 1\n"
_DEAD_MODULE = "def never_called(x):\n    return x * 2\n\ndef also_never_called(y):\n    return y + 1\n"


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _build_orphan_repo(root):
    _write(root, "app/main.py", _LIVE_MAIN)
    _write(root, "app/extra.py", "def unrelated(z):\n    return z\n")
    _write(root, "orphanage/dead.py", _DEAD_MODULE)
    _write(root, "orphanage/extra.py", "def also_unrelated(z):\n    return z - 1\n")


def test_real_pipeline_unreferenced_finding_is_schema_valid(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _build_orphan_repo(root)
    store = FactStore(str(root / "index.db"))
    extract_repo(root, store)
    _, arch = derive_all(store, root.name, root_path=str(root))
    store.close()

    findings = arch.get("findings") or []
    unreferenced = [f for f in findings if f["kind"] == "unreferenced"]
    assert unreferenced, "expected the orphan component to surface as unreferenced"

    doc = build_sarif(arch)
    _validate(doc)
    kinds_in_results = {r["ruleId"] for r in doc["runs"][0]["results"]}
    assert "unreferenced" in kinds_in_results


def test_cli_sarif_flag_end_to_end(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _build_orphan_repo(root)
    out = tmp_path / "architecture.json"
    sarif_out = tmp_path / "findings.sarif"
    result = subprocess.run(
        [sys.executable, "analyze.py", str(root), "-o", str(out),
         "--store", str(tmp_path / "index.db"), "--sarif", str(sarif_out)],
        capture_output=True, text=True, cwd=str(REPO_ROOT), check=True,
    )
    assert sarif_out.is_file(), result.stdout + result.stderr
    assert "SARIF:" in result.stdout
    doc = json.loads(sarif_out.read_text(encoding="utf-8"))
    _validate(doc)


def test_cli_sarif_flag_with_v1_engine_writes_empty_valid_log(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _build_orphan_repo(root)
    out = tmp_path / "architecture.json"
    sarif_out = tmp_path / "findings.sarif"
    result = subprocess.run(
        [sys.executable, "analyze.py", str(root), "-o", str(out),
         "--engine", "v1", "--sarif", str(sarif_out)],
        capture_output=True, text=True, cwd=str(REPO_ROOT), check=True,
    )
    assert "findings require --engine v2" in result.stderr
    doc = json.loads(sarif_out.read_text(encoding="utf-8"))
    _validate(doc)
    assert doc["runs"][0]["results"] == []
