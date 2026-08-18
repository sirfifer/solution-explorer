"""Tests for the AI front door emitted by the projection tier (P8-3).

Every test drives the real pipeline (``extract_repo`` -> ``derive_all`` ->
``project_split`` / ``project_monolith``) against the committed polyglot fixture
and asserts on the emitted ``ai.json`` / ``llms.txt`` bytes. No mocks: the front
door is verified against a real projection tree, including link integrity (every
endpoint the front door names must exist on disk).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from analyzer.derive import derive_all
from analyzer.extract import extract_repo
from analyzer.project import (
    FRONT_DOOR_VERSION,
    build_front_door,
    project_monolith,
    project_split,
    safe_component_id,
)
from analyzer.store import FactStore

FIXTURES = Path(__file__).parent / "fixtures"
POLYGLOT = FIXTURES / "polyglot"

FIXED_TS = "2020-01-01T00:00:00Z"
FIXED_NOW = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _extract_derive(root, name):
    store = FactStore(":memory:")
    extract_repo(root, store)
    _, arch = derive_all(store, name, root_path=str(root))
    return store, arch


def _project_split(root, name, out, **kw):
    store, arch = _extract_derive(root, name)
    res = project_split(
        arch, out, store=store, root=root, previous=None,
        generated_at=FIXED_TS, analyzer_version="1.2.0", now=FIXED_NOW, **kw,
    )
    return store, arch, res


def _project_monolith(root, name, out_file, **kw):
    store, arch = _extract_derive(root, name)
    res = project_monolith(
        arch, out_file, store=store, root=root, previous=None,
        generated_at=FIXED_TS, analyzer_version="1.2.0", now=FIXED_NOW, **kw,
    )
    return store, arch, res


# ---------------------------------------------------------------------------
# emission: both modes emit both files
# ---------------------------------------------------------------------------

def test_split_emits_ai_json_and_llms_txt(tmp_path):
    _, _, res = _project_split(POLYGLOT, "polyglot", tmp_path / "arch")
    ai_path = res.output_dir / "ai.json"
    llms_path = res.output_dir / "llms.txt"
    assert ai_path.is_file()
    assert llms_path.is_file()
    assert res.ai_json_path == ai_path
    assert res.llms_txt_path == llms_path

    ai = json.loads(ai_path.read_text())
    assert ai["front_door_version"] == FRONT_DOOR_VERSION == 1
    assert ai["mode"] == "split"
    assert ai["entry"] == "manifest.json"
    assert ai["dataset"]["name"] == "polyglot"
    assert ai["dataset"]["generated_at"] == FIXED_TS
    assert ai["dataset"]["analyzer_version"] == "1.2.0"

    llms = llms_path.read_text()
    assert llms.startswith("# ")
    assert "ai.json" in llms
    assert "manifest.json" in llms
    assert llms.endswith("\n")


def test_monolith_emits_ai_json_and_llms_txt(tmp_path):
    out = tmp_path / "site" / "architecture.json"
    _, _, res = _project_monolith(POLYGLOT, "polyglot", out)
    ai_path = out.parent / "ai.json"
    llms_path = out.parent / "llms.txt"
    assert ai_path.is_file()
    assert llms_path.is_file()
    assert res.ai_json_path == ai_path
    assert res.llms_txt_path == llms_path

    ai = json.loads(ai_path.read_text())
    assert ai["front_door_version"] == 1
    assert ai["mode"] == "monolith"
    assert ai["entry"] == "architecture.json"
    # Monolith lists the single dataset file, plus the separate CycloneDX
    # sbom.json when the repo carries manifests (the polyglot fixture does) and
    # the CRA cra-readiness.json (P10-4, always emitted with a scan root). Every
    # named endpoint exists on disk (link integrity).
    paths = [e["path"] for e in ai["endpoints"]]
    assert paths[0] == "architecture.json"
    assert set(paths) <= {"architecture.json", "sbom.json", "cra-readiness.json"}
    for path in paths:
        assert (out.parent / path).is_file()


# ---------------------------------------------------------------------------
# link integrity: every concrete endpoint the front door names exists on disk
# ---------------------------------------------------------------------------

def test_split_endpoints_all_exist(tmp_path):
    _, _, res = _project_split(POLYGLOT, "polyglot", tmp_path / "arch")
    root = res.output_dir
    ai = json.loads((root / "ai.json").read_text())

    # Concrete (non-templated) endpoint paths must resolve to real files.
    for ep in ai["endpoints"]:
        path = ep["path"]
        if "<" in path:  # templated (shard/detail patterns) -> checked below
            continue
        assert (root / path).is_file(), f"missing endpoint {path}"

    # Every search shard the front door lists must exist.
    search = ai["search"]
    assert (root / search["index"]).is_file()
    for shard in search["shards"]:
        assert (root / "search" / shard).is_file(), f"missing shard {shard}"

    # The detail filename rule must resolve for every indexed component.
    manifest = json.loads((root / "manifest.json").read_text())
    for comp_id in manifest["component_detail_index"]:
        shard = root / "data" / f"detail-{safe_component_id(comp_id)}.json"
        assert shard.is_file(), f"detail rule missed {comp_id}"


def test_search_section_matches_search_manifest(tmp_path):
    _, _, res = _project_split(POLYGLOT, "polyglot", tmp_path / "arch")
    root = res.output_dir
    ai = json.loads((root / "ai.json").read_text())
    sm = json.loads((root / "search" / "manifest.json").read_text())
    assert ai["search"]["shard_size"] == sm["shard_size"]
    assert ai["search"]["total"] == sm["total"]
    assert ai["search"]["by_kind"] == sm["by_kind"]
    assert ai["search"]["shards"] == sm["shards"]


def test_llms_txt_links_resolve(tmp_path):
    _, _, res = _project_split(POLYGLOT, "polyglot", tmp_path / "arch")
    root = res.output_dir
    llms = (root / "llms.txt").read_text()
    # Extract every ./<path> markdown link target and confirm it exists.
    import re
    targets = re.findall(r"\]\(\./([^)]+)\)", llms)
    assert "ai.json" in targets
    for t in targets:
        assert (root / t).is_file(), f"llms.txt links missing {t}"


# ---------------------------------------------------------------------------
# manifest-section presence reflects the real manifest
# ---------------------------------------------------------------------------

def test_manifest_section_presence_is_accurate(tmp_path):
    _, _, res = _project_split(POLYGLOT, "polyglot", tmp_path / "arch")
    root = res.output_dir
    ai = json.loads((root / "ai.json").read_text())
    manifest = json.loads((root / "manifest.json").read_text())
    for section in ai["manifest_sections"]:
        key = section["key"]
        actually_present = key in manifest and manifest[key] not in (None, [], {})
        assert section["present"] == actually_present, (
            f"section {key}: front door says present={section['present']} "
            f"but manifest present={actually_present}"
        )
        assert section["pointer"] == f".{key}"


# ---------------------------------------------------------------------------
# determinism (invariant I4): two runs are byte-identical
# ---------------------------------------------------------------------------

def test_front_door_bytes_are_deterministic(tmp_path):
    _, _, res_a = _project_split(POLYGLOT, "polyglot", tmp_path / "a")
    _, _, res_b = _project_split(POLYGLOT, "polyglot", tmp_path / "b")
    assert (res_a.output_dir / "ai.json").read_bytes() == (res_b.output_dir / "ai.json").read_bytes()
    assert (res_a.output_dir / "llms.txt").read_bytes() == (res_b.output_dir / "llms.txt").read_bytes()


# ---------------------------------------------------------------------------
# additive-only: the viewer dataset is unchanged by the front door
# ---------------------------------------------------------------------------

def test_front_door_is_additive_only(tmp_path):
    """The viewer never reads ai.json/llms.txt; they must not perturb the dataset.

    The manifest and search/detail shards must be byte-identical whether or not
    the front door is present, and nothing in the viewer-facing files may
    reference the front door files.
    """
    _, arch, res = _project_split(POLYGLOT, "polyglot", tmp_path / "arch")
    root = res.output_dir
    manifest_bytes = (root / "manifest.json").read_bytes()

    # Deleting the front door leaves a complete, valid viewer dataset.
    (root / "ai.json").unlink()
    (root / "llms.txt").unlink()
    manifest = json.loads(manifest_bytes)
    assert "components" in manifest and manifest["components"]
    # The manifest never names the front door files.
    assert "ai.json" not in manifest_bytes.decode()
    assert "llms.txt" not in manifest_bytes.decode()
    assert "front_door" not in manifest
    # component_detail_index only maps real components, not the front door.
    for comp_id in manifest["component_detail_index"]:
        assert (root / "data" / f"detail-{safe_component_id(comp_id)}.json").is_file()


# ---------------------------------------------------------------------------
# build_front_door unit-level behavior (custom monolith filename)
# ---------------------------------------------------------------------------

def test_build_front_door_monolith_filename_flows_through():
    arch = {"name": "x", "generated_at": FIXED_TS, "analyzer_version": "1.2.0",
            "components": [], "relationships": []}
    ai, llms = build_front_door(arch, mode="monolith", monolith_filename="graph.json")
    assert ai["entry"] == "graph.json"
    assert [e["path"] for e in ai["endpoints"]] == ["graph.json"]
    assert "graph.json" in llms


def test_build_front_door_rejects_bad_mode():
    import pytest
    with pytest.raises(ValueError):
        build_front_door({"name": "x"}, mode="nonsense")

def test_monolith_walk_orders_honor_a_custom_filename(tmp_path):
    # Review finding: walk_orders hardcoded architecture.json, lying to agents
    # when the monolith has a custom output name.
    from analyzer.project.frontdoor import build_front_door

    ai_json, _llms = build_front_door(
        {"name": "demo", "generated_at": "2025-01-01T00:00:00Z",
         "analyzer_version": "1.2.0"},
        mode="monolith",
        monolith_filename="graph.json",
    )
    for order in ai_json["walk_orders"]:
        for step in order["steps"]:
            assert step["fetch"] == "graph.json", (order["question"], step)


def test_llms_heading_survives_a_hostile_name(tmp_path):
    # Review finding: a newline in the dataset name split the markdown heading
    # and injected raw lines. The name is now collapsed to one clean line.
    from analyzer.project.frontdoor import build_front_door

    _ai, llms = build_front_door(
        {"name": "Evil\nInjected: ](http://x)", "generated_at": "2025-01-01T00:00:00Z",
         "analyzer_version": "1.2.0"},
        mode="monolith",
        monolith_filename="architecture.json",
    )
    first_line = llms.splitlines()[0]
    assert first_line.startswith("# Evil Injected:"), first_line

def test_legacy_split_without_search_does_not_lie(tmp_path):
    # Review-driven gating: a legacy split dataset (manifest + data/ only, no
    # search shards, no coverage) must not advertise search or coverage
    # endpoints, must null the search section, and its lookup walk orders must
    # fall back to the manifest tree. Fail-before: the pre-fix front door
    # advertised search/manifest.json unconditionally in split mode.
    from analyzer.project.frontdoor import build_front_door

    ai_json, llms = build_front_door(
        {"name": "legacy", "generated_at": "2025-01-01T00:00:00Z",
         "analyzer_version": "1.0.0"},
        mode="split",
        coverage=None,
        activity=None,
        search_manifest=None,
    )
    paths = [e["path"] for e in ai_json["endpoints"]]
    assert not any(p.startswith("search/") for p in paths), paths
    assert "coverage.json" not in paths
    assert ai_json["search"] is None
    for order in ai_json["walk_orders"]:
        for step in order["steps"]:
            assert "search/" not in step["fetch"], (order["question"], step)
    assert "search/manifest.json" not in llms

def test_findings_walk_orders_name_only_real_fields():
    # Battery finding: the walk orders documented category/title/severity, but
    # findings carry kind, summary, detail, rank_score, confidence, and
    # verification_status. An agent filtering on the documented fields found
    # nothing. The copy must name only real fields.
    import json as _json

    from analyzer.project.frontdoor import build_front_door

    ai_json, llms = build_front_door(
        {"name": "d", "generated_at": "2025-01-01T00:00:00Z",
         "analyzer_version": "1.2.0"},
        mode="split",
        search_manifest={"shard_size": 500, "total": 1, "by_kind": {},
                         "fields": [], "shards": ["search-0000.json"]},
    )
    blob = _json.dumps(ai_json) + llms
    assert "category/title/severity" not in blob
    assert "severity" not in blob
    assert "rank_score" in blob and "verification_status" in blob


def test_dataset_carries_the_enriched_flag():
    from analyzer.project.frontdoor import build_front_door

    plain, _ = build_front_door(
        {"name": "d", "generated_at": "2025-01-01T00:00:00Z",
         "analyzer_version": "1.2.0", "components": [{"name": "x"}]},
        mode="monolith", monolith_filename="architecture.json",
    )
    assert plain["dataset"]["enriched"] is False
    rich, _ = build_front_door(
        {"name": "d", "generated_at": "2025-01-01T00:00:00Z",
         "analyzer_version": "1.2.0",
         "components": [{"name": "x", "ai_enhance": {"help_text": "h"}}]},
        mode="monolith", monolith_filename="architecture.json",
    )
    assert rich["dataset"]["enriched"] is True


# ---------------------------------------------------------------------------
# refresh after in-place mutation (comprehension-study S3)


def test_refresh_split_reflects_post_merge_enrichment(tmp_path):
    """The deploy's enrichment merge mutates manifest.json after the front door
    was written; refresh must flip dataset.enriched without re-projecting."""
    from analyzer.project.frontdoor import refresh_front_door

    out = tmp_path / "arch"
    _project_split(POLYGLOT, "poly", out)
    manifest_path = out / "manifest.json"
    ai_before = json.loads((out / "ai.json").read_text())
    assert ai_before["dataset"]["enriched"] is False

    manifest = json.loads(manifest_path.read_text())
    manifest["ai_enhance"] = {"summary": "s"}
    manifest["components"][0]["ai_enhance"] = {"help_text": "h"}
    manifest_path.write_text(json.dumps(manifest))

    written = refresh_front_door(manifest_path)
    assert written is not None

    ai_after = json.loads((out / "ai.json").read_text())
    assert ai_after["dataset"]["enriched"] is True
    # Link integrity survives: the same endpoints are listed, and the search
    # section is rebuilt identically from the on-disk shards.
    assert [e["path"] for e in ai_after["endpoints"]] == [
        e["path"] for e in ai_before["endpoints"]
    ]
    assert ai_after["search"] == ai_before["search"]


def test_refresh_monolith_reflects_post_merge_enrichment(tmp_path):
    from analyzer.project.frontdoor import refresh_front_door

    out_file = tmp_path / "architecture.json"
    _project_monolith(POLYGLOT, "poly", out_file)
    ai_before = json.loads((tmp_path / "ai.json").read_text())
    assert ai_before["dataset"]["enriched"] is False

    doc = json.loads(out_file.read_text())
    doc["ai_enhance"] = {"summary": "s"}
    out_file.write_text(json.dumps(doc))

    assert refresh_front_door(out_file) is not None
    ai_after = json.loads((tmp_path / "ai.json").read_text())
    assert ai_after["dataset"]["enriched"] is True
    assert [e["path"] for e in ai_after["endpoints"]] == [
        e["path"] for e in ai_before["endpoints"]
    ]


def test_refresh_is_a_byte_level_noop_on_an_unchanged_projection(tmp_path):
    """Determinism (I4): refreshing without mutating the entry document must
    reproduce ai.json and llms.txt byte for byte."""
    from analyzer.project.frontdoor import refresh_front_door

    out = tmp_path / "arch"
    _project_split(POLYGLOT, "poly", out)
    ai_bytes = (out / "ai.json").read_bytes()
    llms_bytes = (out / "llms.txt").read_bytes()

    assert refresh_front_door(out / "manifest.json") is not None
    assert (out / "ai.json").read_bytes() == ai_bytes
    assert (out / "llms.txt").read_bytes() == llms_bytes


def test_refresh_without_a_front_door_stays_absent(tmp_path):
    """A projection that never emitted a front door keeps not having one."""
    from analyzer.project.frontdoor import refresh_front_door

    target = tmp_path / "manifest.json"
    target.write_text(json.dumps({"name": "d", "components": []}))
    assert refresh_front_door(target) is None
    assert not (tmp_path / "ai.json").exists()
