"""Tests for scripts/projection-diff.py (card G1, the projection-diff tool).

The tool is a deterministic diff over two full projections. These tests exercise
it two ways: the pure diff functions are imported directly (the script has a
hyphen in its name, so it is loaded via importlib), and the CLI is driven end to
end via subprocess so exit codes, formats, and the on-disk output are asserted
for real, no mocks.

The load-bearing contracts under test:
  - every projection section produces the right added/removed/changed deltas
  - the diff is deterministic: byte-identical inputs give byte-identical output,
    and a changed timestamp is never reported as a change
  - absent sections in an older dataset are treated as empty, so a whole new
    section shows up as additions (additive-projection rule)
  - exit codes: 0 by default, 1 with --exit-code when anything changed, 2 on a
    load error
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DIFF_SCRIPT = REPO_ROOT / "scripts" / "projection-diff.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("projection_diff", DIFF_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pd = _load_module()


def _base_projection() -> dict:
    """A small but complete projection touching every diffable section."""
    return {
        "name": "sample",
        "analyzer_version": "1.2.0",
        "repository": "https://example.com/sample",
        "default_branch": "main",
        "generated_at": "2026-01-01T00:00:00Z",
        "components": [
            {
                "id": "root",
                "name": "root",
                "type": "service",
                "path": ".",
                "language": "python",
                "children": [
                    {
                        "id": "root/api",
                        "name": "api",
                        "type": "module",
                        "path": "api",
                        "language": "python",
                        "children": [],
                    },
                    {
                        "id": "root/web",
                        "name": "web",
                        "type": "module",
                        "path": "web",
                        "language": "typescript",
                        "children": [],
                    },
                ],
            }
        ],
        "relationships": [
            {"source": "root/api", "target": "root/web", "type": "http"},
            {"source": "root/web", "target": "root/api", "type": "import"},
        ],
        "findings": [
            {
                "id": "f:dup:1",
                "kind": "duplication",
                "rank_score": 10.0,
                "verification_status": "unverified",
            },
            {
                "id": "f:unref:2",
                "kind": "unreferenced",
                "rank_score": 5.0,
                "verification_status": "unverified",
            },
        ],
        "coverage": {
            "total": 100,
            "parsed": 90,
            "summary": {"parsed": 90, "binary": 10},
            "inventory": {
                "non_source_total": 10,
                "source_gap_total": 0,
                "dominant": None,
                "groups": [
                    {"id": "grp:build", "label": "Build output", "count": 7},
                    {"id": "grp:media", "label": "Media", "count": 3},
                ],
            },
        },
        "data_entities": [
            {"id": "entity:users", "kind": "table", "name": "users"},
            {"id": "entity:orders", "kind": "table", "name": "orders"},
        ],
        "entity_access": [
            {"accessor_id": "root/api", "entity_id": "entity:users", "mode": "read"},
        ],
        "capabilities": [
            {"id": "cap:http", "kind": "web", "name": "http"},
        ],
        "concerns": [
            {"id": "concern:configuration", "kind": "configuration", "title": "Configuration"},
            {"id": "concern:logging", "kind": "logging", "title": "Logging"},
        ],
        "stats": {
            "total_components": 3,
            "total_files": 5,
            "total_lines": 1000,
            "total_symbols": 200,
            "total_symbols_detected": 200,
            "total_relationships": 2,
            "total_size_bytes": 40000,
            "languages": {"python": 800, "typescript": 200},
        },
        "supply_chain": {
            "counts": {
                "dependencies": 4,
                "direct": 3,
                "transitive": 1,
                "ecosystems": 2,
                "targets": 1,
                "vendored": 0,
                "warnings": 0,
                "pin_status": {"pinned": 2, "range": 2},
                "fixture": {"dependencies": 1, "warnings": 0},
            },
            "dependencies": [
                {"id": "pypi:flask@", "ecosystem": "pypi", "name": "flask"},
                {"id": "pypi:jinja2@", "ecosystem": "pypi", "name": "jinja2"},
                {"id": "npm:react@", "ecosystem": "npm", "name": "react"},
                {"id": "npm:vite@", "ecosystem": "npm", "name": "vite"},
            ],
        },
    }


def _write(tmp_path: Path, name: str, data: dict) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Pure-function tests
# ---------------------------------------------------------------------------


def test_identical_projections_have_no_changes():
    base = _base_projection()
    diff = pd.diff_projections(base, base)
    assert diff["has_changes"] is False
    assert all(v is False for v in diff["changed_sections"].values())


def test_flatten_components_walks_children():
    base = _base_projection()
    flat = pd.flatten_components(base)
    assert set(flat) == {"root", "root/api", "root/web"}


def test_component_added_removed_and_changed():
    old = _base_projection()
    new = _base_projection()
    # add a component, remove one, change the type of another
    new["components"][0]["children"].append(
        {"id": "root/db", "name": "db", "type": "datastore", "path": "db"}
    )
    new["components"][0]["children"] = [
        c for c in new["components"][0]["children"] if c["id"] != "root/web"
    ]
    new["components"][0]["children"][0]["type"] = "package"  # root/api type change

    c = pd.diff_projections(old, new)["sections"]["components"]
    assert c["added"] == ["root/db"]
    assert c["removed"] == ["root/web"]
    assert len(c["changed"]) == 1
    assert c["changed"][0]["id"] == "root/api"
    assert c["changed"][0]["fields"]["type"] == {"old": "module", "new": "package"}


def test_relationship_deltas_by_kind():
    old = _base_projection()
    new = _base_projection()
    new["relationships"] = [
        {"source": "root/web", "target": "root/api", "type": "import"},
        {"source": "root/api", "target": "root/db", "type": "uses"},
    ]
    r = pd.diff_projections(old, new)["sections"]["relationships"]
    assert r["by_kind"]["http"] == {"old": 1, "new": 0}
    assert r["by_kind"]["uses"] == {"old": 0, "new": 1}
    assert r["added"] == ["root/api -> root/db (uses)"]
    assert r["removed"] == ["root/api -> root/web (http)"]


def test_finding_new_resolved_and_changed():
    old = _base_projection()
    new = _base_projection()
    # resolve f:unref:2, add a new finding, change rank + status of f:dup:1
    new["findings"] = [
        {
            "id": "f:dup:1",
            "kind": "duplication",
            "rank_score": 42.0,
            "verification_status": "confirmed",
        },
        {
            "id": "f:new:3",
            "kind": "inconsistency",
            "rank_score": 1.0,
            "verification_status": "unverified",
        },
    ]
    f = pd.diff_projections(old, new)["sections"]["findings"]
    assert f["new"] == [{"id": "f:new:3", "kind": "inconsistency"}]
    assert f["resolved"] == [{"id": "f:unref:2", "kind": "unreferenced"}]
    assert len(f["changed"]) == 1
    changed = f["changed"][0]
    assert changed["id"] == "f:dup:1"
    assert changed["rank_score"] == {"old": 10.0, "new": 42.0}
    assert changed["verification_status"] == {"old": "unverified", "new": "confirmed"}


def test_coverage_and_inventory_deltas():
    old = _base_projection()
    new = _base_projection()
    new["coverage"]["total"] = 102
    new["coverage"]["summary"]["binary"] = 12
    new["coverage"]["inventory"]["non_source_total"] = 12
    new["coverage"]["inventory"]["groups"][0]["count"] = 9  # grp:build 7 -> 9
    sections = pd.diff_projections(old, new)["sections"]
    cov = sections["coverage"]
    assert cov["total"] == {"old": 100, "new": 102}
    assert cov["summary"]["binary"] == {"old": 10, "new": 12}
    inv = sections["inventory"]
    assert inv["scalars"]["non_source_total"] == {"old": 10, "new": 12}
    assert inv["groups"]["grp:build"]["old"] == 7
    assert inv["groups"]["grp:build"]["new"] == 9


def test_data_entity_capability_and_access_deltas():
    old = _base_projection()
    new = _base_projection()
    new["data_entities"] = [{"id": "entity:users", "kind": "table", "name": "users"}]
    new["capabilities"].append({"id": "cap:cli", "kind": "cli", "name": "cli"})
    new["entity_access"].append(
        {"accessor_id": "root/web", "entity_id": "entity:orders", "mode": "write"}
    )
    sections = pd.diff_projections(old, new)["sections"]
    assert sections["data_entities"]["removed"] == ["entity:orders"]
    assert sections["capabilities"]["added"] == ["cap:cli"]
    assert sections["entity_access"]["added"] == ["root/web write entity:orders"]


def test_enrichment_coverage_delta():
    old = _base_projection()
    new = _base_projection()
    new["components"][0]["children"][0]["ai_enhance"] = {"description": "x"}
    new["ai_enhance"] = {"summary": "s"}
    e = pd.diff_projections(old, new)["sections"]["enrichment"]
    assert e["old"]["component_enriched"] == 0
    assert e["new"]["component_enriched"] == 1
    assert e["old"]["architecture_enriched"] is False
    assert e["new"]["architecture_enriched"] is True


def test_timestamp_change_is_not_a_change():
    old = _base_projection()
    new = _base_projection()
    new["generated_at"] = "2027-12-31T23:59:59Z"
    diff = pd.diff_projections(old, new)
    assert diff["has_changes"] is False


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.__setitem__("coverage", [{"total": 1}]),
        lambda p: p["coverage"].__setitem__("summary", ["parsed", "binary"]),
        lambda p: p["coverage"].__setitem__("inventory", ["x"]),
        lambda p: p.__setitem__("components", "not-a-list"),
        lambda p: p.__setitem__("relationships", {"weird": "dict"}),
        lambda p: p.__setitem__("stats", ["not", "a", "dict"]),
        lambda p: p.__setitem__("supply_chain", ["nope"]),
        lambda p: p["supply_chain"].__setitem__("counts", "not-a-dict"),
        lambda p: p.__setitem__("concerns", {"weird": "dict"}),
    ],
)
def test_malformed_section_types_degrade_not_crash(mutate):
    # A section shaped wrong (list where dict expected, or vice versa) must
    # degrade to empty, never abort the diff. Regression for adversarial-review
    # finding 1 (truthy-but-wrong-type slipped past the `or {}` guard).
    old = _base_projection()
    new = _base_projection()
    mutate(new)
    diff = pd.diff_projections(old, new)  # must not raise
    assert "sections" in diff


def test_nan_rank_score_is_not_a_change():
    # json.load accepts NaN; NaN != NaN would flag a spurious change on
    # byte-identical input. Regression for adversarial-review finding 2.
    proj = _base_projection()
    proj["findings"][0]["rank_score"] = float("nan")
    diff = pd.diff_projections(proj, proj)
    assert diff["has_changes"] is False


def test_inventory_group_without_id_still_diffed():
    # A group lacking an id must still register a delta (keyed by label),
    # not be silently dropped. Regression for the adversarial-review minor note.
    old = _base_projection()
    new = _base_projection()
    old["coverage"]["inventory"]["groups"].append(
        {"label": "Orphan cache", "count": 4}
    )  # present old, gone new
    inv = pd.diff_projections(old, new)["sections"]["inventory"]
    assert "Orphan cache" in inv["groups"]
    assert inv["groups"]["Orphan cache"] == {"label": "Orphan cache", "old": 4, "new": None}


def test_absent_sections_treated_as_empty():
    # An older dataset with no findings/capabilities/entities at all.
    old = {"name": "old", "components": [{"id": "root"}], "relationships": []}
    new = _base_projection()
    diff = pd.diff_projections(old, new)
    # findings appearing wholesale shows up as new findings, not a crash
    assert diff["sections"]["findings"]["new"]
    assert diff["sections"]["capabilities"]["added"] == ["cap:http"]
    assert diff["has_changes"] is True


# ---------------------------------------------------------------------------
# Stats, supply_chain, and concerns (the G1 diff extension: catches the gross
# extraction / broken-SBOM regressions the identity-keyed sections above miss)
# ---------------------------------------------------------------------------


def test_stats_symbol_halving_registers_drift():
    # The exact false-clean the G2 adversarial review proved: symbols are not a
    # diffed section, so before this extension a symbol-extraction pass that
    # silently halved its output passed the golden `check` with no drift. The
    # stats roll-up is the section that now catches it.
    old = _base_projection()
    new = _base_projection()
    new["stats"]["total_symbols"] = 100  # was 200: halved
    new["stats"]["total_symbols_detected"] = 100
    diff = pd.diff_projections(old, new)
    assert diff["has_changes"] is True
    assert diff["changed_sections"]["stats"] is True
    d = diff["sections"]["stats"]["deltas"]
    assert d["total_symbols"] == {"old": 200, "new": 100}
    assert d["total_symbols_detected"] == {"old": 200, "new": 100}


def test_stats_totals_and_per_language_deltas():
    old = _base_projection()
    new = _base_projection()
    new["stats"]["total_files"] = 6
    new["stats"]["total_lines"] = 1100
    new["stats"]["languages"]["python"] = 900
    new["stats"]["languages"]["go"] = 50  # a language appearing
    d = pd.diff_projections(old, new)["sections"]["stats"]["deltas"]
    assert d["total_files"] == {"old": 5, "new": 6}
    assert d["total_lines"] == {"old": 1000, "new": 1100}
    assert d["languages.python"] == {"old": 800, "new": 900}
    assert d["languages.go"] == {"old": None, "new": 50}  # absence reads as None


def test_supply_chain_count_and_warning_deltas():
    old = _base_projection()
    new = _base_projection()
    # A broken SBOM pass: dependency count drops, warnings appear, a pin bucket
    # shifts. All roll into the flattened counts delta.
    new["supply_chain"]["counts"]["dependencies"] = 2
    new["supply_chain"]["counts"]["warnings"] = 3
    new["supply_chain"]["counts"]["pin_status"]["range"] = 1
    diff = pd.diff_projections(old, new)
    assert diff["has_changes"] is True
    assert diff["changed_sections"]["supply_chain"] is True
    sc = diff["sections"]["supply_chain"]
    assert sc["counts"]["dependencies"] == {"old": 4, "new": 2}
    assert sc["counts"]["warnings"] == {"old": 0, "new": 3}
    assert sc["counts"]["pin_status.range"] == {"old": 2, "new": 1}


def test_supply_chain_per_ecosystem_delta():
    old = _base_projection()
    new = _base_projection()
    # Drop both npm deps: pypi is unchanged, npm regresses to zero. The
    # per-ecosystem view surfaces a single-ecosystem regression even when the
    # overall total also moves.
    new["supply_chain"]["dependencies"] = [
        d for d in new["supply_chain"]["dependencies"] if d["ecosystem"] != "npm"
    ]
    sc = pd.diff_projections(old, new)["sections"]["supply_chain"]
    assert sc["by_ecosystem"]["npm"] == {"old": 2, "new": 0}
    assert "pypi" not in sc["by_ecosystem"]  # unchanged, not reported


def test_concerns_added_and_removed():
    old = _base_projection()
    new = _base_projection()
    new["concerns"] = [
        {"id": "concern:configuration", "kind": "configuration", "title": "Configuration"},
        {"id": "concern:persistence", "kind": "persistence", "title": "Persistence"},
    ]
    con = pd.diff_projections(old, new)["sections"]["concerns"]
    assert con["added"] == ["concern:persistence"]
    assert con["removed"] == ["concern:logging"]


def test_absent_stats_supply_chain_concerns_degrade_to_empty():
    # Additive-projection rule: an older dataset that predates these sections
    # diffs cleanly. Wholesale appearance is additions, and a dataset with none
    # of the sections is identical to itself (no spurious drift).
    old = {"name": "old", "components": [{"id": "root"}], "relationships": []}
    new = _base_projection()
    diff = pd.diff_projections(old, new)  # must not raise
    assert diff["changed_sections"]["stats"] is True
    assert diff["changed_sections"]["supply_chain"] is True
    assert diff["changed_sections"]["concerns"] is True
    same = pd.diff_projections(old, old)
    assert same["changed_sections"]["stats"] is False
    assert same["changed_sections"]["supply_chain"] is False
    assert same["changed_sections"]["concerns"] is False


def test_render_text_includes_new_sections():
    old = _base_projection()
    new = _base_projection()
    new["stats"]["total_symbols"] = 50
    new["supply_chain"]["counts"]["warnings"] = 2
    new["concerns"].append(
        {"id": "concern:persistence", "kind": "persistence", "title": "P"}
    )
    text = pd.render_text(pd.diff_projections(old, new))
    assert "Stats:" in text
    assert "total_symbols: 200 -> 50 (-150)" in text
    assert "Supply chain:" in text
    assert "Concerns:" in text


# ---------------------------------------------------------------------------
# CLI end-to-end tests
# ---------------------------------------------------------------------------


def _run(*args):
    return subprocess.run(
        [sys.executable, str(DIFF_SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def test_cli_identical_exit_zero_and_message(tmp_path):
    p = _write(tmp_path, "a.json", _base_projection())
    res = _run(str(p), str(p))
    assert res.returncode == 0
    assert "No changes" in res.stdout


def test_cli_exit_code_flag_signals_change(tmp_path):
    old = _write(tmp_path, "old.json", _base_projection())
    changed = _base_projection()
    changed["capabilities"].append({"id": "cap:cli", "kind": "cli", "name": "cli"})
    new = _write(tmp_path, "new.json", changed)
    # default: exit 0 even with changes
    assert _run(str(old), str(new)).returncode == 0
    # with --exit-code: exit 1
    assert _run(str(old), str(new), "--exit-code").returncode == 1
    # with --exit-code but no change: exit 0
    assert _run(str(old), str(old), "--exit-code").returncode == 0


def test_cli_json_output_is_complete_and_deterministic(tmp_path):
    old = _write(tmp_path, "old.json", _base_projection())
    changed = _base_projection()
    changed["findings"] = changed["findings"][1:]
    new = _write(tmp_path, "new.json", changed)
    r1 = _run(str(old), str(new), "--format", "json")
    r2 = _run(str(old), str(new), "--format", "json")
    assert r1.returncode == 0
    assert r1.stdout == r2.stdout  # byte-identical
    payload = json.loads(r1.stdout)
    assert payload["schema"] == "solution-explorer/projection-diff/v1"
    assert payload["has_changes"] is True
    assert payload["sections"]["findings"]["resolved"]


def test_cli_output_to_file(tmp_path):
    p = _write(tmp_path, "a.json", _base_projection())
    out = tmp_path / "diff.txt"
    res = _run(str(p), str(p), "--output", str(out))
    assert res.returncode == 0
    assert out.exists()
    assert "No changes" in out.read_text(encoding="utf-8")


def test_cli_missing_file_exits_two(tmp_path):
    p = _write(tmp_path, "a.json", _base_projection())
    res = _run(str(tmp_path / "nope.json"), str(p))
    assert res.returncode == 2
    assert "not found" in res.stderr


def test_cli_malformed_json_exits_two(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid", encoding="utf-8")
    good = _write(tmp_path, "good.json", _base_projection())
    res = _run(str(bad), str(good))
    assert res.returncode == 2
    assert "not valid JSON" in res.stderr


@pytest.mark.parametrize("fmt", ["text", "json"])
def test_cli_formats_run_clean(tmp_path, fmt):
    old = _write(tmp_path, "old.json", _base_projection())
    changed = _base_projection()
    changed["relationships"] = changed["relationships"][:1]
    new = _write(tmp_path, "new.json", changed)
    res = _run(str(old), str(new), "--format", fmt)
    assert res.returncode == 0
    assert res.stdout.strip()
