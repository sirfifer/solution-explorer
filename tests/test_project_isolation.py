"""Fault-isolation proof for the projection driver (card R1 wave 2).

Behavioral tests over the REAL extract -> derive -> project path (no mocking of
the unit under test): a temp repo is written to disk, extracted into a fact
store, derived, and projected. A fault is injected into a REAL projection
emitter (the emitter function itself is replaced with one that raises, exactly
as a genuine bug in that emitter would behave), and we prove the projection run
completes with a deterministic honest gap on the delivered artifact instead of
crashing or shipping a fracture.

Fail-before context: before R1 wave 2, project_split / project_monolith called
each emitter as a bare statement, so any emitter raising propagated straight out
and crashed the whole projection. These tests would fail (raise) against that
pre-wave-2 code; they pass now because each emitter runs under per-unit
isolation and the main writer (manifest / architecture.json) is written last,
carrying every gap, degrading to a skeleton on its own failure.
"""

from __future__ import annotations

import json

import pytest

from analyzer.derive import derive_all
from analyzer.derive import relationships as rel_pass
from analyzer.extract import extract_repo
from analyzer.project import pipeline as pipe
from analyzer.store import FactStore

FIXED_TS = "2026-01-01T00:00:00Z"


def _boom(*_args, **_kwargs):
    raise RuntimeError("injected emitter fault")


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _build_repo(root):
    _write(root, "app/main.py", "def handler(req):\n    return {'ok': True}\n")
    _write(root, "app/db.py", "class User:\n    id = 0\n    name = ''\n")
    _write(root, "README.md", "# Sample\n\nA small sample application.\n")


def _extract(root) -> FactStore:
    (root / ".se").mkdir(parents=True, exist_ok=True)
    store = FactStore(str(root / ".se" / "index.db"))
    extract_repo(root, store)
    return store


def _split(root, store, out) -> dict:
    """Run a real split projection and return the loaded manifest dict."""
    _, arch = derive_all(store, "sample", root_path=str(root))
    pipe.project_split(
        arch, out, store=store, root=root,
        generated_at=FIXED_TS, analyzer_version="1.2.0",
    )
    return json.loads((out / "manifest.json").read_text(encoding="utf-8"))


def _monolith(root, store, out_path) -> dict:
    """Run a real monolith projection and return the loaded architecture dict."""
    _, arch = derive_all(store, "sample", root_path=str(root))
    pipe.project_monolith(
        arch, out_path, store=store, root=root,
        generated_at=FIXED_TS, analyzer_version="1.2.0",
    )
    return json.loads(out_path.read_text(encoding="utf-8"))


def _producers(doc: dict) -> set[str]:
    return {g["producer"] for g in doc.get("gaps", [])}


# ---------------------------------------------------------------------------
# byte-parity guard: a clean run adds no gaps key
# ---------------------------------------------------------------------------


def test_healthy_split_records_no_gaps_key(tmp_path):
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    manifest = _split(tmp_path, store, tmp_path / "out")
    assert "gaps" not in manifest
    assert manifest["components"]  # a whole projection
    store.close()


def test_healthy_monolith_records_no_gaps_key(tmp_path):
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    doc = _monolith(tmp_path, store, tmp_path / "architecture.json")
    assert "gaps" not in doc
    assert doc["components"]
    store.close()


# ---------------------------------------------------------------------------
# sidecar emitter failures: honest gap, artifact absent, main projection whole
# ---------------------------------------------------------------------------


def test_failing_sbom_emitter_degrades_to_gap(tmp_path, monkeypatch):
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    monkeypatch.setattr(pipe, "emit_sbom", _boom)
    out = tmp_path / "out"
    manifest = _split(tmp_path, store, out)  # must NOT raise
    gap = next((g for g in manifest["gaps"] if g["producer"] == "project.sbom"), None)
    assert gap is not None
    assert gap["stage"] == "project"
    assert gap["status"] == "failed"
    assert gap["reason"] == "RuntimeError: injected emitter fault"
    # The main projection is whole and the failed sidecar is simply absent.
    assert manifest["components"]
    assert "supply_chain" not in manifest
    assert not (out / "sbom.json").exists()
    store.close()


def test_failing_coverage_build_degrades_to_gap(tmp_path, monkeypatch):
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    monkeypatch.setattr(pipe, "build_coverage", _boom)
    out = tmp_path / "out"
    manifest = _split(tmp_path, store, out)  # must NOT raise
    assert "project.coverage" in _producers(manifest)
    assert manifest["components"]
    assert not (out / "coverage.json").exists()
    store.close()


def test_failing_search_shards_gap_rides_on_the_manifest(tmp_path, monkeypatch):
    # Search shards run BEFORE the manifest write (wave-2 reorder) precisely so a
    # sidecar gap still reaches the main artifact written last.
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    monkeypatch.setattr(pipe, "write_search_shards", _boom)
    manifest = _split(tmp_path, store, tmp_path / "out")  # must NOT raise
    assert "project.search-shards" in _producers(manifest)
    assert manifest["components"]
    store.close()


def test_failing_frontdoor_gap_rides_on_the_manifest(tmp_path, monkeypatch):
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    monkeypatch.setattr(pipe, "write_front_door", _boom)
    out = tmp_path / "out"
    manifest = _split(tmp_path, store, out)  # must NOT raise
    assert "project.frontdoor" in _producers(manifest)
    assert manifest["components"]
    assert not (out / "ai.json").exists()
    store.close()


def test_failing_gitinfo_degrades_to_gap_and_defaults(tmp_path, monkeypatch):
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    monkeypatch.setattr(pipe, "read_git_info", _boom)
    manifest = _split(tmp_path, store, tmp_path / "out")  # must NOT raise
    assert "project.gitinfo" in _producers(manifest)
    # The safe default is applied: no repository URL, "main" branch.
    assert manifest["default_branch"] == "main"
    assert manifest["components"]
    store.close()


# ---------------------------------------------------------------------------
# main-writer failures: skeleton fallback, run always ships a well-formed artifact
# ---------------------------------------------------------------------------


def test_failing_manifest_writer_degrades_to_skeleton_and_gap(tmp_path, monkeypatch):
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    monkeypatch.setattr(pipe, "write_manifest_and_details", _boom)
    out = tmp_path / "out"
    manifest = _split(tmp_path, store, out)  # must NOT raise; skeleton written
    # The skeleton is whole and contract-shaped: empty collections, empty index,
    # zeroed stats, and it carries the manifest writer's OWN failure gap.
    assert "project.manifest" in _producers(manifest)
    assert manifest["components"] == []
    assert manifest["component_detail_index"] == {}
    assert manifest["stats"]["total_components"] == 0
    assert manifest["name"] == "sample"
    store.close()


def test_failing_monolith_writer_degrades_to_skeleton_and_gap(tmp_path, monkeypatch):
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    monkeypatch.setattr(pipe, "write_monolith", _boom)
    out_path = tmp_path / "architecture.json"
    doc = _monolith(tmp_path, store, out_path)  # must NOT raise; skeleton written
    assert "project.monolith" in _producers(doc)
    assert doc["components"] == []
    assert doc["symbols"] == []
    assert doc["files"] == []
    assert doc["stats"]["total_relationships"] == 0
    assert doc["name"] == "sample"
    store.close()


def test_monolith_sidecar_gap_rides_in_architecture_json(tmp_path, monkeypatch):
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    monkeypatch.setattr(pipe, "emit_sbom", _boom)
    doc = _monolith(tmp_path, store, tmp_path / "architecture.json")  # must NOT raise
    assert "project.sbom" in _producers(doc)
    assert doc["components"]  # the real monolith still shipped whole
    store.close()


# ---------------------------------------------------------------------------
# determinism and cross-tier combination
# ---------------------------------------------------------------------------


def test_injected_project_gap_is_deterministic_across_runs(tmp_path, monkeypatch):
    # Same input, same gap: two fresh extractions of identical content with the
    # same injected fault must produce byte-identical gap records, so parity and
    # the golden gate hold even on a degraded run.
    monkeypatch.setattr(pipe, "emit_sbom", _boom)
    seen = []
    for i in range(2):
        root = tmp_path / f"run{i}"
        _build_repo(root)
        store = _extract(root)
        manifest = _split(root, store, root / "out")
        seen.append(manifest.get("gaps"))
        store.close()
    assert seen[0] == seen[1]
    assert seen[0]  # non-empty


def test_derive_and_project_gaps_coexist_on_the_manifest(tmp_path, monkeypatch):
    # A derive-tier gap and a project-tier gap must both ride on the delivered
    # manifest, proving the two gap sources are merged (not one clobbering the
    # other) and never double-counted.
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    monkeypatch.setattr(rel_pass, "derive_relationships", _boom)  # derive tier
    monkeypatch.setattr(pipe, "emit_sbom", _boom)                 # project tier
    manifest = _split(tmp_path, store, tmp_path / "out")
    producers = _producers(manifest)
    assert "derive.relationships" in producers
    assert "project.sbom" in producers
    # No duplicate records for a single producer (merge, not concatenate-twice).
    all_producers = [g["producer"] for g in manifest["gaps"]]
    assert len(all_producers) == len(set(all_producers))
    store.close()


# ---------------------------------------------------------------------------
# adversarial-review hardening (PR #74 findings)
# ---------------------------------------------------------------------------


def test_failed_search_is_not_advertised_in_the_front_door(tmp_path, monkeypatch):
    # Finding 2: a failed search write yields the empty-manifest default (a truthy
    # dict), which must NOT make the front door advertise a search index that was
    # never written. The front door must emit its honest search-absent contract.
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    monkeypatch.setattr(pipe, "write_search_shards", _boom)
    out = tmp_path / "out"
    manifest = _split(tmp_path, store, out)
    assert "project.search-shards" in _producers(manifest)
    assert not (out / "search" / "manifest.json").exists()
    ai = json.loads((out / "ai.json").read_text(encoding="utf-8"))
    assert ai["search"] is None  # honest: no lying search endpoint
    store.close()


def test_healthy_search_is_still_advertised(tmp_path):
    # Guard for the fix above: a real (successful) search index is advertised, so
    # the "failed -> None" logic did not suppress a genuine index.
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    out = tmp_path / "out"
    manifest = _split(tmp_path, store, out)
    assert "gaps" not in manifest
    ai = json.loads((out / "ai.json").read_text(encoding="utf-8"))
    assert ai["search"] is not None
    assert (out / "search" / "manifest.json").exists()
    store.close()


def test_skeleton_manifest_prunes_orphan_detail_shards(tmp_path, monkeypatch):
    # Finding 4: when the manifest writer fails after (partially) writing detail
    # shards, the skeleton declares an empty detail index, so any shards already
    # on disk are orphans. They are pruned so the tree matches the manifest.
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    out = tmp_path / "out"
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "data" / "detail-stale.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pipe, "write_manifest_and_details", _boom)
    manifest = _split(tmp_path, store, out)  # skeleton path
    assert "project.manifest" in _producers(manifest)
    assert manifest["component_detail_index"] == {}
    assert not (out / "data" / "detail-stale.json").exists()  # orphan pruned
    store.close()


def test_non_serializable_identity_field_degrades_without_crash(tmp_path, monkeypatch):
    # Finding 1: a circular object in an identity field that reaches BOTH the real
    # manifest writer and the skeleton must not crash the run. The skeleton
    # coerces identity fields to JSON-safe scalars, so it still ships a manifest;
    # the Isolator fallback guard is the final backstop. Here the arch description
    # is circular and the real writer is forced to fail, driving the skeleton.
    _build_repo(tmp_path)
    store = _extract(tmp_path)
    circular: dict = {}
    circular["self"] = circular

    _, arch = derive_all(store, "sample", root_path=str(tmp_path))
    arch["description"] = circular  # a non-serializable identity field
    monkeypatch.setattr(pipe, "write_manifest_and_details", _boom)
    out = tmp_path / "out"
    # Must NOT raise (no cascading crash) and must ship a well-formed manifest.
    pipe.project_split(
        arch, out, store=store, root=tmp_path,
        generated_at=FIXED_TS, analyzer_version="1.2.0",
    )
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert "project.manifest" in _producers(manifest)
    assert isinstance(manifest["description"], str)  # coerced, serializable
    store.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
