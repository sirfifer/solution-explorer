"""The projection linter, proved by mutation.

A linter that has only ever seen good input is worthless: it will report PASS
for the same reason a disconnected smoke alarm does. So the fixture here builds
one small, complete, internally consistent projection, asserts it lints clean,
and then breaks it one defect at a time, asserting that the specific rule meant
to catch that defect actually fires.

Every mutation below is a defect class we have really shipped or really feared:
a dangling relationship endpoint, a stale detail shard left behind by a previous
dataset, an index whose counts disagree with its payload, a lens row pointing at
a component that is gone, a search hit that navigates nowhere, a stat that
contradicts its own tree, a citation into a file that does not exist, and a
half-enriched projection.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "lint-projection.py"


def _load():
    spec = importlib.util.spec_from_file_location("lint_projection", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    # Registered before exec because @dataclass resolves its own module out of
    # sys.modules; a hyphenated script loaded by path is absent from it.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


lp = _load()


# --------------------------------------------------------------------- fixture


SOURCES = {
    "alpha/one.py": "def one():\n    return 1\n",
    "alpha/two.py": "class Two:\n    pass\n",
    "beta/three.py": "def three():\n    return 3\n",
}


def _component(cid: str, name: str, path: str, files: list[str], children=None) -> dict:
    return {
        "id": cid,
        "name": name,
        "type": "module",
        "path": path,
        "language": "python",
        "framework": "",
        "description": "",
        "children": children or [],
        "files": files,
        "entry_points": [],
        "config_files": [],
        "metrics": {"files": len(files), "lines": 2, "size_bytes": 32, "symbols": len(files)},
    }


def _symbol(cid: str, path: str, name: str, kind: str, line: int, end: int) -> dict:
    return {
        "id": f". {cid} {path} {name}",
        "name": name,
        "kind": kind,
        "file": path,
        "line": line,
        "end_line": end,
        "parent": None,
        "visibility": "public",
    }


def _file(path: str) -> dict:
    return {"path": path, "language": "python", "lines": 2, "size_bytes": 32,
            "imports": [], "exports": [], "symbols": [], "module_doc": ""}


@pytest.fixture
def projection(tmp_path: Path) -> Path:
    """A small projection that is whole in every band the linter checks."""
    src = tmp_path / "src"
    for rel, text in SOURCES.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    out = tmp_path / "proj"
    (out / "data").mkdir(parents=True)
    (out / "search").mkdir(parents=True)

    alpha = _component("alpha", "alpha", "alpha", ["alpha/one.py", "alpha/two.py"])
    beta = _component("beta", "beta", "beta", ["beta/three.py"])
    root = _component("root", "demo", ".", [], children=[alpha, beta])

    symbols = {
        "alpha": [
            _symbol("alpha", "alpha/one.py", "one", "function", 1, 2),
            _symbol("alpha", "alpha/two.py", "Two", "class", 1, 2),
        ],
        "beta": [_symbol("beta", "beta/three.py", "three", "function", 1, 2)],
        "root": [],
    }
    files_by_comp = {
        "alpha": [_file("alpha/one.py"), _file("alpha/two.py")],
        "beta": [_file("beta/three.py")],
        "root": [],
    }
    detail_index = {}
    for cid in ("root", "alpha", "beta"):
        detail_index[cid] = {
            "fileCount": len(files_by_comp[cid]),
            "symbolCount": len(symbols[cid]),
        }
        (out / "data" / f"detail-{cid}.json").write_text(
            json.dumps({"files": files_by_comp[cid], "symbols": symbols[cid]},
                       indent=2, sort_keys=True),
            encoding="utf-8",
        )

    relationships = [{
        "source": "alpha", "target": "beta", "type": "import",
        "confidence": "inferred", "label": "beta",
        "evidence": [{"file": "alpha/one.py", "line": 1, "snippet": "beta"}],
    }]

    manifest = {
        "name": "demo",
        "description": "",
        "repository": "",
        "default_branch": "main",
        "generated_at": "2026-08-23T00:00:00+00:00",
        "analyzer_version": "1.0.0",
        "root_path": str(src),
        "components": [root],
        "relationships": relationships,
        "repositories": [],
        "stats": {
            "total_components": 3,
            "total_files": 3,
            "total_symbols": 3,
            "total_relationships": 1,
            "total_lines": 6,
        },
        "component_detail_index": detail_index,
        "changelog": [{"changes": [
            {"kind": "component_added", "target_id": "alpha", "target_name": "alpha",
             "target_type": "module", "detail": "New component discovered"},
            {"kind": "relationship_added", "target_id": "alpha->beta",
             "target_name": "alpha->beta", "target_type": "import", "detail": "New edge"},
        ]}],
        "changelog_serial": 1,
        "capabilities": [{"component_id": "alpha", "confidence": "inferred",
                          "evidence": [{"file": "alpha/one.py", "line": 1, "snippet": "one"}]}],
        "rules": [{"component_id": "beta", "confidence": "inferred",
                   "evidence": [{"file": "beta/three.py", "line": 1, "snippet": "three"}]}],
        "findings": [{"confidence": "inferred", "detail": {"component_ids": ["alpha"]},
                      "evidence": [{"file": "alpha/two.py", "line": 1}]}],
        "concerns": [{"id": "concern:auth", "kind": "auth", "basis": "test",
                      "members": [{"component_id": "beta", "evidence": [], "files": []}]}],
        "data_entities": [{"id": "entity:alpha:thing", "component_id": "alpha",
                           "fields": [], "evidence": []}],
        "entity_access": [{"accessor_id": "beta", "entity_id": "entity:alpha:thing",
                           "mode": "read", "confidence": "inferred", "evidence": []}],
        "coverage": {"total": 3, "parsed": 3, "summary": {"parsed": 3}},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    search_entries = [
        {"ref_kind": "component", "ref_id": "alpha", "name": "alpha", "path": "alpha",
         "component": "alpha", "text": ""},
        {"ref_kind": "file", "ref_id": "alpha/one.py", "name": "one.py", "path": "alpha/one.py",
         "component": "alpha", "text": ""},
        {"ref_kind": "symbol", "ref_id": ". alpha alpha/one.py one", "name": "one",
         "path": "alpha/one.py", "component": "alpha", "text": ""},
    ]
    (out / "search" / "search-0000.json").write_text(
        json.dumps(search_entries, indent=2, sort_keys=True), encoding="utf-8")
    (out / "search" / "manifest.json").write_text(json.dumps({
        "version": 1, "shards": ["search-0000.json"], "shard_size": 2000,
        "total": len(search_entries),
        "by_kind": {"component": 1, "file": 1, "symbol": 1},
        "fields": ["ref_kind", "ref_id", "name", "path", "component", "text"],
    }, indent=2, sort_keys=True), encoding="utf-8")

    (out / "ai.json").write_text(json.dumps({
        "front_door_version": 1, "kind": "solution-explorer/front-door", "mode": "split",
        "projection_root": ".", "entry": "manifest.json",
        "dataset": {"enriched": False},
        "endpoints": [{"path": "manifest.json"}, {"path": "search/manifest.json"}],
        "manifest_sections": [{"key": "components", "present": True},
                              {"key": "relationships", "present": True}],
        "detail_shards": {"pattern": "data/detail-<id>.json"},
        "search": {"manifest": "search/manifest.json"},
        "walk_orders": [], "token_economy": {},
    }, indent=2, sort_keys=True), encoding="utf-8")
    # The manifest's coverage section is a claim; coverage.json is the payload.
    # Writing only one of the two is itself a defect the linter reports, so the
    # whole fixture writes both.
    (out / "coverage.json").write_text(json.dumps({
        "total": 3, "parsed": 3, "summary": {"parsed": 3}, "rows": [],
    }, indent=2, sort_keys=True), encoding="utf-8")
    (out / "llms.txt").write_text("# demo\n", encoding="utf-8")
    return out


def _run(proj: Path, **kw) -> lp.Report:
    policy = dict(lp.DEFAULT_POLICY)
    policy.update(kw.pop("policy", {}))
    src = kw.pop("src", None)
    if src is None:
        manifest = json.loads((proj / "manifest.json").read_text(encoding="utf-8"))
        src = Path(manifest["root_path"])
    return lp.Linter(proj, src, policy, content_sample=kw.pop("content_sample", 100)).run()


def _rules(report: lp.Report, severity: str = "error") -> set[str]:
    return {f.rule for f in report.findings if f.severity == severity}


def _edit_manifest(proj: Path, mutate) -> None:
    path = proj / "manifest.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    mutate(doc)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")


# ----------------------------------------------------------------- the control


def test_a_whole_projection_lints_clean(projection: Path) -> None:
    """The control. Without this every mutation test below proves nothing."""
    report = _run(projection)
    assert not report.errors, [f.render() for f in report.errors]
    assert report.census["components"] == 3
    assert report.census["max_depth"] == 1
    assert report.census["enriched"]["share"] == 0.0


def test_census_reports_are_present_even_when_clean(projection: Path) -> None:
    report = _run(projection)
    for key in ("components", "relationships", "detail_shards", "depth_histogram",
                "empty_nodes", "lens_population", "citations_checked"):
        assert key in report.census


# ------------------------------------------------------------------- parse.*


def test_missing_manifest_is_fatal(tmp_path: Path) -> None:
    empty = tmp_path / "nothing"
    empty.mkdir()
    report = lp.Linter(empty, None, dict(lp.DEFAULT_POLICY)).run()
    assert "parse.missing" in _rules(report)


def test_invalid_json_manifest_is_fatal(projection: Path) -> None:
    (projection / "manifest.json").write_text("{not json", encoding="utf-8")
    report = lp.Linter(projection, None, dict(lp.DEFAULT_POLICY)).run()
    assert "parse.invalid_json" in _rules(report)


def test_missing_llms_txt_is_caught(projection: Path) -> None:
    (projection / "llms.txt").unlink()
    assert "parse.missing" in _rules(_run(projection))


# --------------------------------------------------------------------- ref.*


def test_dangling_relationship_endpoint(projection: Path) -> None:
    _edit_manifest(projection, lambda d: d["relationships"][0].__setitem__("target", "ghost"))
    assert "ref.relationship_endpoint" in _rules(_run(projection))


def test_detail_shard_missing_from_disk(projection: Path) -> None:
    (projection / "data" / "detail-beta.json").unlink()
    assert "ref.detail_shard_missing" in _rules(_run(projection))


def test_stale_shard_left_behind_by_a_previous_dataset(projection: Path) -> None:
    (projection / "data" / "detail-gamma.json").write_text(
        json.dumps({"files": [], "symbols": []}), encoding="utf-8")
    assert "ref.detail_shard_orphan" in _rules(_run(projection))


def test_component_with_no_index_entry(projection: Path) -> None:
    _edit_manifest(projection, lambda d: d["component_detail_index"].pop("beta"))
    report = _run(projection)
    assert "ref.detail_index" in _rules(report)
    assert "ref.detail_shard_orphan" in _rules(report)


def test_index_counts_disagree_with_the_shard(projection: Path) -> None:
    _edit_manifest(projection, lambda d: d["component_detail_index"]["alpha"].__setitem__("symbolCount", 99))
    assert "count.detail_index" in _rules(_run(projection))


def test_component_declares_a_file_its_shard_does_not_carry(projection: Path) -> None:
    def mutate(d):
        for c in d["components"][0]["children"]:
            if c["id"] == "alpha":
                c["files"].append("alpha/phantom.py")
                c["metrics"]["files"] = len(c["files"])
        d["component_detail_index"]["alpha"]["fileCount"] = 3
    _edit_manifest(projection, mutate)
    assert "ref.component_files" in _rules(_run(projection))


def test_duplicate_component_id(projection: Path) -> None:
    def mutate(d):
        children = d["components"][0]["children"]
        children.append(dict(children[0]))
    _edit_manifest(projection, mutate)
    assert "ref.duplicate_component_id" in _rules(_run(projection))


def test_lens_row_points_at_a_missing_component(projection: Path) -> None:
    _edit_manifest(projection, lambda d: d["capabilities"][0].__setitem__("component_id", "ghost"))
    assert "ref.lens_component" in _rules(_run(projection))


def test_concern_member_points_at_a_missing_component(projection: Path) -> None:
    _edit_manifest(projection, lambda d: d["concerns"][0]["members"][0].__setitem__("component_id", "ghost"))
    assert "ref.lens_component" in _rules(_run(projection))


def test_finding_points_at_a_missing_component(projection: Path) -> None:
    _edit_manifest(projection, lambda d: d["findings"][0]["detail"].__setitem__("component_ids", ["ghost"]))
    assert "ref.finding_component" in _rules(_run(projection))


def test_entity_access_points_at_a_missing_entity(projection: Path) -> None:
    _edit_manifest(projection, lambda d: d["entity_access"][0].__setitem__("entity_id", "entity:ghost"))
    assert "ref.entity_access" in _rules(_run(projection))


def test_changelog_edge_target_is_split_into_endpoints(projection: Path) -> None:
    """An edge id is "source->target"; both halves must resolve, neither the whole."""
    clean = _run(projection)
    assert "ref.changelog_target" not in _rules(clean)
    _edit_manifest(projection, lambda d: d["changelog"][0]["changes"][1].__setitem__("target_id", "alpha->ghost"))
    assert "ref.changelog_target" in _rules(_run(projection))


def test_search_hit_that_navigates_nowhere(projection: Path) -> None:
    path = projection / "search" / "search-0000.json"
    entries = json.loads(path.read_text(encoding="utf-8"))
    entries[0]["ref_id"] = "ghost"
    path.write_text(json.dumps(entries), encoding="utf-8")
    assert "ref.search_entry" in _rules(_run(projection))


def test_search_manifest_totals_must_match_the_shards(projection: Path) -> None:
    path = projection / "search" / "manifest.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["total"] = 99
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert "count.search_total" in _rules(_run(projection))


def test_front_door_advertises_an_endpoint_that_is_not_there(projection: Path) -> None:
    path = projection / "ai.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["endpoints"].append({"path": "nope.json"})
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert "ref.front_door_endpoint" in _rules(_run(projection))


def test_front_door_section_claim_must_match_the_manifest(projection: Path) -> None:
    """The S3 defect class: a surface claiming a posture the payload lacks."""
    path = projection / "ai.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["manifest_sections"].append({"key": "supply_chain", "present": True})
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert "ref.front_door_section" in _rules(_run(projection))


# ------------------------------------------------------------------- count.*


def test_stats_that_contradict_the_tree(projection: Path) -> None:
    _edit_manifest(projection, lambda d: d["stats"].__setitem__("total_components", 42))
    assert "count.stats_components" in _rules(_run(projection))


def test_stats_that_contradict_the_shards(projection: Path) -> None:
    _edit_manifest(projection, lambda d: d["stats"].__setitem__("total_symbols", 42))
    assert "count.stats_symbols" in _rules(_run(projection))


def test_component_metrics_that_contradict_its_file_list(projection: Path) -> None:
    def mutate(d):
        for c in d["components"][0]["children"]:
            if c["id"] == "alpha":
                c["metrics"]["files"] = 9
    _edit_manifest(projection, mutate)
    assert "count.component_metrics" in _rules(_run(projection))


def test_coverage_ledger_that_does_not_add_up(projection: Path) -> None:
    _edit_manifest(projection, lambda d: d["coverage"].__setitem__("total", 10))
    assert "count.coverage_ledger" in _rules(_run(projection))


# ------------------------------------------------------------------ source.*


def test_citation_into_a_file_that_does_not_exist(projection: Path) -> None:
    _edit_manifest(
        projection,
        lambda d: d["relationships"][0]["evidence"][0].__setitem__("file", "alpha/ghost.py"),
    )
    assert "source.citation_file" in _rules(_run(projection))


def test_citation_past_the_end_of_its_file(projection: Path) -> None:
    _edit_manifest(
        projection,
        lambda d: d["relationships"][0]["evidence"][0].__setitem__("line", 9999),
    )
    assert "source.citation_line" in _rules(_run(projection))


def test_shard_file_that_is_not_in_the_source_tree(projection: Path) -> None:
    path = projection / "data" / "detail-beta.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["files"][0]["path"] = "beta/ghost.py"
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert "source.file_missing" in _rules(_run(projection))


def test_component_path_that_is_not_in_the_source_tree(projection: Path) -> None:
    def mutate(d):
        for c in d["components"][0]["children"]:
            if c["id"] == "beta":
                c["path"] = "beta-moved"
    _edit_manifest(projection, mutate)
    assert "source.component_path" in _rules(_run(projection))


def test_symbols_off_their_declared_line(projection: Path) -> None:
    """A whole-shard line-base error, the class a per-file check would miss."""
    for cid in ("alpha", "beta"):
        path = projection / "data" / f"detail-{cid}.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        for s in doc["symbols"]:
            s["line"] = 2
            s["end_line"] = 2
        path.write_text(json.dumps(doc), encoding="utf-8")
    assert "source.symbol_line" in _rules(_run(projection))


def test_source_band_skips_loudly_when_there_is_no_source_tree(projection: Path) -> None:
    report = lp.Linter(projection, None, dict(lp.DEFAULT_POLICY)).run()
    assert any(prefix == "source.*" for prefix, _ in report.skipped)
    assert "source.citation_file" not in _rules(report)


# ------------------------------------------------------------------ census.*


def test_partial_enrichment_is_an_error_under_the_enriched_profile(projection: Path) -> None:
    def mutate(d):
        d["components"][0]["children"][0]["ai_enhance"] = {"help_text": "x"}
    _edit_manifest(projection, mutate)
    report = _run(projection, policy={"profile": "enriched"})
    assert "census.enrichment_profile" in _rules(report)
    assert report.census["enriched"]["count"] == 1


def test_enrichment_leaking_into_a_deterministic_run_is_an_error(projection: Path) -> None:
    def mutate(d):
        for c in d["components"][0]["children"]:
            c["ai_enhance"] = {"help_text": "x"}
    _edit_manifest(projection, mutate)
    assert "census.enrichment_profile" in _rules(_run(projection, policy={"profile": "deterministic"}))


def test_partial_enrichment_is_allowed_only_as_a_disclosed_private_evaluation(
    projection: Path,
) -> None:
    def mutate(d):
        d["components"][0]["children"][0]["ai_enhance"] = {"help_text": "x"}

    _edit_manifest(projection, mutate)
    (projection / "publication.json").write_text(json.dumps({
        "purpose": "evaluation",
        "header": {"banner": "Private partial-enrichment human evaluation."},
        "footer": {"always": ["AI enrichment covers 1 of 3 components."]},
        "access": {"visibility": "private-preview"},
    }), encoding="utf-8")

    report = _run(projection, policy={"profile": "evaluation"})
    assert "census.enrichment_profile" not in _rules(report)


def test_partial_evaluation_without_exact_visible_scope_is_an_error(
    projection: Path,
) -> None:
    def mutate(d):
        d["components"][0]["children"][0]["ai_enhance"] = {"help_text": "x"}

    _edit_manifest(projection, mutate)
    (projection / "publication.json").write_text(json.dumps({
        "purpose": "evaluation",
        "header": {"banner": "Private partial-enrichment human evaluation."},
        "footer": {"always": ["Some components are enhanced."]},
        "access": {"visibility": "private-preview"},
    }), encoding="utf-8")

    report = _run(projection, policy={"profile": "evaluation"})
    assert "census.enrichment_profile" in _rules(report)


def test_a_flat_tree_on_a_large_subject_is_an_error(projection: Path) -> None:
    def mutate(d):
        children = d["components"][0]["children"]
        d["components"] = children          # drop the root, leaving a flat list
        d["component_detail_index"].pop("root")
        d["stats"]["total_components"] = len(children)
    _edit_manifest(projection, mutate)
    (projection / "data" / "detail-root.json").unlink()
    report = _run(projection, policy={"min_depth_over_components": [2, 2]})
    assert "census.depth" in _rules(report)


def test_dead_end_components_are_counted_and_thresholded(projection: Path) -> None:
    def mutate(d):
        for c in d["components"][0]["children"]:
            c["files"] = []
            c["metrics"]["files"] = 0
        d["stats"]["total_files"] = 0
        d["stats"]["total_symbols"] = 0
        d["component_detail_index"] = {k: {"fileCount": 0, "symbolCount": 0}
                                       for k in d["component_detail_index"]}
    _edit_manifest(projection, mutate)
    for cid in ("alpha", "beta"):
        (projection / "data" / f"detail-{cid}.json").write_text(
            json.dumps({"files": [], "symbols": []}), encoding="utf-8")
    report = _run(projection)
    assert "census.empty_nodes" in _rules(report)
    assert report.census["empty_nodes"]["count"] == 2


def test_a_required_lens_that_lost_its_whole_array(projection: Path) -> None:
    _edit_manifest(projection, lambda d: d.__setitem__("capabilities", []))
    report = _run(projection, policy={"require_populated": ["capabilities"]})
    assert "census.lens_empty" in _rules(report)


# ----------------------------------------------------------------- hygiene.*


def test_absolute_path_leak_is_a_warning_not_a_failure(projection: Path) -> None:
    report = _run(projection)
    assert "hygiene.root_path" in _rules(report, "warn")
    assert not report.errors


# ---------------------------------------------------------------- exit codes


def test_exit_codes(projection: Path, tmp_path: Path, capsys) -> None:
    out = tmp_path / "lint.json"
    assert lp.main([str(projection), "--json", str(out), "--quiet"]) == 0
    assert lp.main([str(projection), "--quiet", "--strict"]) == 2   # the root_path warning
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["errors"] == 0 and doc["lint_version"] == 1

    _edit_manifest(projection, lambda d: d["relationships"][0].__setitem__("target", "ghost"))
    assert lp.main([str(projection), "--quiet"]) == 1
    assert lp.main([str(tmp_path / "does-not-exist"), "--quiet"]) == 3


# ------------------------------------------------------- census.parser_degraded


def _stock_projection_with(proj: Path, languages: dict, symbols: list) -> None:
    """Give the fixture a language mix and a symbol population to judge.

    The stock fixture is a toy: three Python files and a handful of symbols. This
    band only speaks when a subject is big enough for the absence of methods to
    mean something, so a test of it has to supply that scale explicitly rather
    than mutate one field and hope.
    """
    _edit_manifest(proj, lambda d: (d.setdefault("stats", {}).update({"languages": languages})))
    shard = proj / "data" / "detail-alpha.json"
    doc = json.loads(shard.read_text(encoding="utf-8"))
    doc["symbols"] = symbols
    shard.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")


def _symbol_population(methods: int, functions: int, classes: int) -> list:
    out = []
    for kind, count in (("method", methods), ("function", functions), ("class", classes)):
        for i in range(count):
            out.append({
                "id": f"{kind}:{i}", "name": f"{kind}{i}", "kind": kind,
                "file": "alpha/one.py", "line": 1,
            })
    return out


def test_classes_without_methods_are_a_degraded_parser(projection: Path) -> None:
    """The regression test for a real incident.

    A private large-repository validation corpus run was launched with an interpreter that had no tree-sitter, so
    every TypeScript file fell back to the regex parser. The analyzer reported
    100% coverage and 0 gaps throughout, because every file genuinely WAS parsed.
    What no check noticed was that none of them was parsed well: 55 methods
    survived against 14,744 classes.
    """
    _stock_projection_with(
        projection,
        {"typescript": 3_000_000, "json": 100_000},
        _symbol_population(methods=55, functions=90_000, classes=14_744),
    )
    report = _run(projection)
    assert "census.parser_degraded" in _rules(report, "error")


def test_a_healthy_method_share_is_not_flagged(projection: Path) -> None:
    """The other half of the calibration: the good run must stay quiet.

    Measured on the same commit parsed properly: 28,501 methods over 4,292
    classes. A band that cannot tell that from the degraded shape would be
    reporting noise on every healthy projection, which is worse than not
    existing.
    """
    _stock_projection_with(
        projection,
        {"typescript": 3_000_000, "json": 100_000},
        _symbol_population(methods=28_501, functions=9_794, classes=4_292),
    )
    report = _run(projection)
    assert "census.parser_degraded" not in _rules(report, "error")


def test_a_small_or_method_free_subject_says_nothing(projection: Path) -> None:
    """No opinion where there is no evidence.

    A subject with few classes, or one written in languages whose parser emits no
    method kind at all, must not be accused. Silence here is the correct answer,
    not a missed defect.
    """
    _stock_projection_with(
        projection,
        {"python": 400_000},
        _symbol_population(methods=0, functions=5_000, classes=800),
    )
    report = _run(projection)
    assert "census.parser_degraded" not in _rules(report, "error")
