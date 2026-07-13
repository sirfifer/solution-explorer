"""Tests for the Tier 4 projection tier (P4-5).

Every test drives the real pipeline: ``extract_repo`` into a ``FactStore``,
``derive_all``, then the projection functions, against the committed parity
fixtures or constructed temp repos. Assertions are on observable projected
output, not reimplemented logic.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from analyzer.cli import safe_component_id as cli_safe_component_id
from analyzer.derive import derive_all
from analyzer.extract import extract_repo
from analyzer.parsers import PARSERS
from analyzer.project import (
    build_search_entries,
    project_monolith,
    project_split,
    safe_component_id,
    shard_entries,
)
from analyzer.project.changelog import apply_changelog
from analyzer.project.gitinfo import apply_info_plist_names, read_git_info
from analyzer.store import FactStore

FIXTURES = Path(__file__).parent / "fixtures"
POLYGLOT = FIXTURES / "polyglot"
MULTI_CONFIG = FIXTURES / "multi" / "solution.json"

_PARITY_LANGS = ("python", "swift", "rust", "typescript", "javascript", "go", "ruby")
_TS = all(getattr(PARSERS.get(x), "_ts_available", False) for x in _PARITY_LANGS)
requires_ts = pytest.mark.skipif(
    not _TS, reason="fixtures are pinned to the tree-sitter tier")

FIXED_TS = "2020-01-01T00:00:00Z"
FIXED_NOW = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _extract_derive(root, name):
    store = FactStore(":memory:")
    extract_repo(root, store)
    _, arch = derive_all(store, name, root_path=str(root))
    return store, arch


def _project(root, name, out, **kw):
    store, arch = _extract_derive(root, name)
    res = project_split(
        arch, out, store=store, root=root, previous=None,
        generated_at=FIXED_TS, analyzer_version="1.2.0", now=FIXED_NOW, **kw,
    )
    return store, arch, res


# ---------------------------------------------------------------------------
# schema compatibility with the viewer (App.tsx / types.ts)
# ---------------------------------------------------------------------------

def test_manifest_is_schema_compatible(tmp_path):
    _, _, res = _project(POLYGLOT, "polyglot", tmp_path / "arch")
    manifest = json.loads(res.manifest_path.read_text())
    # App.tsx reads components/relationships/stats from the manifest and expects
    # symbols/files to be absent (they move into detail shards).
    assert manifest["components"]
    assert "relationships" in manifest
    assert manifest["stats"]["total_components"] > 0
    assert "symbols" not in manifest
    assert "files" not in manifest
    assert "component_detail_index" in manifest


def test_detail_shards_carry_symbols_and_files(tmp_path):
    _, arch, res = _project(POLYGLOT, "polyglot", tmp_path / "arch")
    data_dir = res.output_dir / "data"
    # Every indexed component has a detail shard keyed by the escape convention.
    manifest = json.loads(res.manifest_path.read_text())
    for comp_id, counts in manifest["component_detail_index"].items():
        shard = data_dir / f"detail-{safe_component_id(comp_id)}.json"
        assert shard.is_file(), f"missing shard for {comp_id}"
        detail = json.loads(shard.read_text())
        assert set(detail.keys()) == {"symbols", "files"}
        assert len(detail["files"]) == counts["fileCount"]
        assert len(detail["symbols"]) == counts["symbolCount"]


def test_monolith_is_self_contained(tmp_path):
    store, arch = _extract_derive(POLYGLOT, "polyglot")
    out = tmp_path / "architecture.json"
    project_monolith(arch, out, store=store, root=POLYGLOT, previous=None,
                     generated_at=FIXED_TS, analyzer_version="1.2.0", now=FIXED_NOW)
    doc = json.loads(out.read_text())
    # Monolith inlines the arrays App.tsx loads directly on the fallback path.
    assert doc["symbols"] and doc["files"]
    assert doc["stats"]["total_symbols"] == len(doc["symbols"])
    assert "coverage" in doc


# ---------------------------------------------------------------------------
# escape convention (F-CRIT-5 three-implementation cross-check, P0-3 fixtures)
# ---------------------------------------------------------------------------

def test_escape_matches_cli_and_p0_3_fixtures():
    # The P0-3 shared fixture ids (tests/test_cli.py, viewer + worker
    # componentId.test) and their expected escapes.
    cases = {
        "viewer/src": "viewer--src",
        "repo:unamentis": "repo__unamentis",
        "repo:unamentis/viewer": "repo__unamentis--viewer",
        "plain-id": "plain-id",
    }
    for raw, expected in cases.items():
        assert safe_component_id(raw) == expected
        # And it must agree with the old-engine implementation exactly.
        assert safe_component_id(raw) == cli_safe_component_id(raw)


# ---------------------------------------------------------------------------
# optional new keys (evidence/confidence/origin, nested parents)
# ---------------------------------------------------------------------------

@requires_ts
def test_relationships_carry_evidence_confidence_origin(tmp_path):
    _, _, res = _project(POLYGLOT, "polyglot", tmp_path / "arch")
    manifest = json.loads(res.manifest_path.read_text())
    rels = manifest["relationships"]
    assert rels, "fixture has at least one relationship"
    for rel in rels:
        assert "evidence" in rel and isinstance(rel["evidence"], list)
        assert rel.get("confidence") in ("certain", "inferred", "ai")
        assert rel.get("origin") in ("static", "config", "ai")
    # At least one edge points at a real call site.
    http = [r for r in rels if r["type"] == "http"]
    assert http and http[0]["evidence"], "http edge must carry evidence"


@requires_ts
def test_nested_symbol_parents_present_in_shards(tmp_path):
    _, _, res = _project(POLYGLOT, "polyglot", tmp_path / "arch")
    parented = []
    for shard in (res.output_dir / "data").glob("detail-*.json"):
        for sym in json.loads(shard.read_text())["symbols"]:
            if sym.get("parent"):
                parented.append(sym)
    assert parented, "nested symbols (with parent) must survive into shards"
    # Every parent id resolves to a symbol present somewhere in the projection.
    all_ids = set()
    for shard in (res.output_dir / "data").glob("detail-*.json"):
        all_ids.update(s["id"] for s in json.loads(shard.read_text())["symbols"])
    for sym in parented:
        assert sym["parent"] in all_ids


# ---------------------------------------------------------------------------
# coverage ledger (absorbs P4-4 item 1; invariant I2)
# ---------------------------------------------------------------------------

def test_coverage_summary_in_manifest_matches_store(tmp_path):
    store, _, res = _project(POLYGLOT, "polyglot", tmp_path / "arch")
    manifest = json.loads(res.manifest_path.read_text())
    assert manifest["coverage"]["summary"] == store.coverage_summary()
    assert manifest["coverage"]["parsed"] == store.coverage_summary().get("parsed")


def test_coverage_shard_has_full_rows(tmp_path):
    store, _, res = _project(POLYGLOT, "polyglot", tmp_path / "arch")
    cov = json.loads(res.coverage_path.read_text())
    assert cov["rows"] == store.coverage()
    assert cov["total"] == sum(cov["summary"].values())
    # The polyglot fixture has two unsupported-extension exclusions.
    dispositions = {r["disposition"] for r in cov["rows"]}
    assert "parsed" in dispositions
    assert any(d.startswith("excluded:") for d in dispositions)


def test_coverage_dispositions_carry_reasons(tmp_path):
    # Build a repo that forces several dispositions and assert the projection
    # surfaces each with its rule/reason (no silent skip, I2).
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("x = 1\n")
    (repo / "notes.unknownext").write_text("data\n")  # unsupported_extension
    (repo / "blob.bin").write_bytes(b"\x00\x01\x02\x00")  # binary
    (repo / "big.py").write_text("y = 2\n" * 5000)  # opt-in max_file_size

    store = FactStore(":memory:")
    extract_repo(repo, store, max_file_size=100)
    _, arch = derive_all(store, "repo", root_path=str(repo))
    res = project_split(arch, tmp_path / "out", store=store, root=repo, previous=None,
                        generated_at=FIXED_TS, analyzer_version="1.2.0", now=FIXED_NOW)
    cov = json.loads(res.coverage_path.read_text())
    by_path = {r["path"]: r for r in cov["rows"]}
    assert by_path["notes.unknownext"]["disposition"] == "excluded:unsupported_extension"
    assert by_path["blob.bin"]["disposition"] == "binary"
    assert by_path["big.py"]["disposition"] == "excluded:max_file_size"
    # Every excluded/failed row names a rule or reason (no bare "skipped").
    for row in cov["rows"]:
        if row["disposition"].startswith("excluded:") or row["disposition"] == "failed":
            assert row["disposition"] != "excluded:" and row["disposition"] != "skipped"


# ---------------------------------------------------------------------------
# search shards (emit + unit test now; viewer consumes in P6-4)
# ---------------------------------------------------------------------------

def test_search_shards_cover_names_paths_descriptions_docstrings(tmp_path):
    _, arch, res = _project(POLYGLOT, "polyglot", tmp_path / "arch")
    sm = json.loads((res.output_dir / "search" / "manifest.json").read_text())
    entries = []
    for name in sm["shards"]:
        entries.extend(json.loads((res.output_dir / "search" / name).read_text()))
    assert len(entries) == sm["total"]
    kinds = {e["ref_kind"] for e in entries}
    assert {"component", "file", "symbol"} <= kinds
    # Names, paths present; a component with a description carries text.
    assert all("name" in e and "path" in e and "text" in e for e in entries)
    # A known symbol name is findable.
    sym_names = {e["name"] for e in entries if e["ref_kind"] == "symbol"}
    assert any(n for n in sym_names)
    # File paths appear as searchable entries.
    file_paths = {e["ref_id"] for e in entries if e["ref_kind"] == "file"}
    assert "services/api/api/server.py" in file_paths


def test_search_enrichment_channel_from_store_and_arch():
    # Store overlay help text and inline component ai_enhance help text both
    # land as enrichment search entries.
    # Distinct targets so both channels produce distinct entries (an inline and
    # a store entry for the SAME component id correctly dedupe to one).
    store = FactStore(":memory:")
    store.add_enrichment("component", "svc", {"help_text": "handles auth tokens"})
    arch = {
        "components": [
            {"id": "svc", "name": "Service", "path": "svc",
             "description": "the service", "files": [], "children": []},
            {"id": "web", "name": "Web", "path": "web",
             "description": "the web app", "files": [], "children": [],
             "ai_enhance": {"help_text": "inline overview text"}},
        ],
        "files": [], "symbols": [], "relationships": [],
    }
    entries = build_search_entries(arch, store)
    enrich = [e for e in entries if e["ref_kind"] == "enrichment"]
    texts = {e["text"] for e in enrich}
    assert "handles auth tokens" in texts  # store overlay channel
    assert "inline overview text" in texts  # inline arch channel


def test_search_entries_sorted_and_sharded():
    arch = {
        "components": [{"id": f"c{i}", "name": f"c{i}", "path": f"c{i}",
                        "files": [], "children": []} for i in range(5)],
        "files": [], "symbols": [], "relationships": [],
    }
    entries = build_search_entries(arch, None)
    assert entries == sorted(entries, key=lambda e: (e["ref_kind"], e["ref_id"]))
    bundle = shard_entries(entries, shard_size=2)
    assert bundle["manifest"]["total"] == len(entries)
    assert len(bundle["manifest"]["shards"]) == (len(entries) + 1) // 2
    # Concatenating shards in manifest order reproduces the sorted entry list.
    recombined = []
    for name in bundle["manifest"]["shards"]:
        recombined.extend(bundle["shards"][name])
    assert recombined == entries


# ---------------------------------------------------------------------------
# changelog: store-vs-previous-projection diff, serials, equivalence
# ---------------------------------------------------------------------------

def test_changelog_serials_preserved_across_projections(tmp_path):
    out = tmp_path / "arch"
    # First projection: initial entry, serial 1.
    store1, arch1 = _extract_derive(POLYGLOT, "polyglot")
    r1 = project_split(arch1, out, store=store1, root=POLYGLOT,
                       generated_at=FIXED_TS, analyzer_version="1.2.0", now=FIXED_NOW)
    assert r1.changelog_serial == 1
    m1 = json.loads(r1.manifest_path.read_text())
    assert len(m1["changelog"]) == 1
    assert m1["changelog"][0]["scan_type"] == "initial"

    # Second projection into the same dir with no structural change: serial
    # advances to 2, but no new entry is appended (no changes).
    store2, arch2 = _extract_derive(POLYGLOT, "polyglot")
    r2 = project_split(arch2, out, store=store2, root=POLYGLOT,
                       generated_at=FIXED_TS, analyzer_version="1.2.0", now=FIXED_NOW)
    assert r2.changelog_serial == 2
    m2 = json.loads(r2.manifest_path.read_text())
    assert len(m2["changelog"]) == 1  # unchanged, no new entry


def test_changelog_equivalent_to_current_behavior():
    # Drive a scripted change sequence and assert the projection changelog
    # matches the current-engine IncrementalAnalyzer output entry-for-entry
    # (ignoring the wall-clock timestamp).
    from analyzer.incremental import IncrementalAnalyzer

    before = {
        "components": [
            {"id": "a", "name": "A", "type": "module", "metrics": {"lines": 10}, "children": []},
            {"id": "b", "name": "B", "type": "module", "metrics": {"lines": 5}, "children": []},
        ],
        "relationships": [{"source": "a", "target": "b", "type": "import"}],
    }
    after = {
        "components": [
            # a modified (metrics change), b removed, c added
            {"id": "a", "name": "A", "type": "module", "metrics": {"lines": 20}, "children": []},
            {"id": "c", "name": "C", "type": "service", "metrics": {"lines": 3}, "children": []},
        ],
        "relationships": [{"source": "a", "target": "c", "type": "http"}],
    }

    # Projection path.
    proj = copy.deepcopy(after)
    apply_changelog(proj, before, now=FIXED_NOW)

    # Current-engine path (exactly what analyzer/cli.py _apply_changelog runs).
    ia = object.__new__(IncrementalAnalyzer)
    ia.head_sha = ""
    diff = ia.compute_diff_summary(before, after)
    prev_serial = before.get("changelog_serial", 0)
    entry = ia.build_changelog_entry(diff, before, after, "full", prev_serial + 1)
    expected = copy.deepcopy(after)
    IncrementalAnalyzer._append_changelog(expected, entry, before)

    assert proj["changelog_serial"] == expected["changelog_serial"]
    # Compare entries field-by-field except the timestamp.
    pe = proj["changelog"][-1]
    ee = expected["changelog"][-1]
    for key in ("serial", "commit_sha", "scan_type", "summary", "changes"):
        assert pe[key] == ee[key], f"changelog field {key} diverged"


# ---------------------------------------------------------------------------
# determinism (invariant I4)
# ---------------------------------------------------------------------------

def _digest_dir(d: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(Path(d).rglob("*")):
        if p.is_file():
            h.update(p.relative_to(d).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def test_projection_is_byte_deterministic(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    _project(POLYGLOT, "polyglot", a)
    _project(POLYGLOT, "polyglot", b)
    assert _digest_dir(a) == _digest_dir(b)


def test_determinism_across_process_hash_seeds():
    script = (
        "import json,hashlib,sys,tempfile,os;"
        "from pathlib import Path;"
        "from datetime import datetime,timezone;"
        "from analyzer.store import FactStore;"
        "from analyzer.extract import extract_repo;"
        "from analyzer.derive import derive_all;"
        "from analyzer.project import project_split;"
        "d=tempfile.mkdtemp();"
        "s=FactStore(':memory:');"
        f"extract_repo({str(POLYGLOT)!r}, s);"
        f"_,a=derive_all(s,'polyglot',root_path={str(POLYGLOT)!r});"
        "project_split(a, Path(d)/'arch', store=s, previous=None,"
        "  generated_at='2020-01-01T00:00:00Z', analyzer_version='1.2.0',"
        "  now=datetime(2020,1,1,tzinfo=timezone.utc));"
        "h=hashlib.sha256();"
        "[ (h.update(p.relative_to(d).as_posix().encode()), h.update(p.read_bytes()))"
        "  for p in sorted(Path(d).rglob('*')) if p.is_file()];"
        "print(h.hexdigest())"
    )
    repo_root = os.path.dirname(os.path.dirname(__file__))

    def run(seed):
        out = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True,
            env=dict(os.environ, PYTHONHASHSEED=seed), cwd=repo_root, check=True,
        )
        return out.stdout

    assert run("0") == run("1") == run("12345")


# ---------------------------------------------------------------------------
# environment facts at projection time (P4-3 deferrals)
# ---------------------------------------------------------------------------

def test_git_info_read_and_credentials_stripped(tmp_path):
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "config").write_text(
        "[remote \"origin\"]\n"
        "\turl = https://x-access-token:SECRETTOKEN@github.com/org/private.git\n"
    )
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/develop\n")
    repository, branch = read_git_info(repo)
    assert repository == "https://github.com/org/private"
    assert "SECRETTOKEN" not in repository
    assert "x-access-token" not in repository
    assert branch == "develop"


def test_git_info_flows_into_projection_without_token(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("z = 1\n")
    (repo / ".git").mkdir(parents=True)
    (repo / ".git" / "config").write_text(
        "[remote \"origin\"]\n"
        "\turl = https://x-access-token:LEAKME@github.com/org/private.git\n"
    )
    (repo / ".git" / "HEAD").write_text("ref: refs/heads/trunk\n")
    store = FactStore(":memory:")
    extract_repo(repo, store)
    _, arch = derive_all(store, "repo", root_path=str(repo))
    out = tmp_path / "arch"
    res = project_split(arch, out, store=store, root=repo, previous=None,
                        generated_at=FIXED_TS, analyzer_version="1.2.0", now=FIXED_NOW)
    blob = res.manifest_path.read_text()
    assert "LEAKME" not in blob
    manifest = json.loads(blob)
    assert manifest["repository"] == "https://github.com/org/private"
    assert manifest["default_branch"] == "trunk"


def test_info_plist_name_applied_at_projection_time(tmp_path):
    # A component carrying an Info.plist config entry gets its name overridden
    # from the plist at projection time (the derive tier leaves the dir name).
    import plistlib

    root = tmp_path / "root"
    app_dir = root / "MyAppDir"
    app_dir.mkdir(parents=True)
    plist_path = app_dir / "Info.plist"
    with open(plist_path, "wb") as fh:
        plistlib.dump({"CFBundleDisplayName": "Fancy App"}, fh)

    components = [{
        "id": "MyAppDir", "name": "MyAppDir", "type": "application",
        "config_files": [{"type": "Info.plist", "path": "MyAppDir/Info.plist"}],
        "children": [],
    }]
    overridden = apply_info_plist_names(components, root)
    assert overridden == 1
    assert components[0]["name"] == "Fancy App"


# ---------------------------------------------------------------------------
# multi-repo projection
# ---------------------------------------------------------------------------

@requires_ts
def test_multi_repo_projection(tmp_path):
    from analyzer.derive import derive_multi_from_config

    arch = derive_multi_from_config(MULTI_CONFIG)
    out = tmp_path / "arch"
    # No single store/root for the merged multi-repo dict; coverage is omitted.
    res = project_split(arch, out, store=None, root=None, previous=None,
                        generated_at=FIXED_TS, analyzer_version="1.2.0", now=FIXED_NOW)
    manifest = json.loads(res.manifest_path.read_text())
    assert "coverage" not in manifest  # no unified ledger for merged repos yet
    # repo:<name> container components produce escaped shard filenames.
    repo_ids = [c["id"] for c in manifest["components"] if c["id"].startswith("repo:")]
    assert repo_ids
    for rid in repo_ids:
        shard = out / "data" / f"detail-{safe_component_id(rid)}.json"
        assert shard.is_file()
        assert "__" in shard.name  # repo: -> repo__


# ---------------------------------------------------------------------------
# opt-in CLI flag (EXPERIMENTAL)
# ---------------------------------------------------------------------------

def test_cli_engine_v2_split_end_to_end(tmp_path):
    out = tmp_path / "site"
    repo_root = os.path.dirname(os.path.dirname(__file__))
    result = subprocess.run(
        [sys.executable, "analyze.py", str(POLYGLOT), "-o", str(out),
         "--split", "--engine", "v2"],
        capture_output=True, text=True, cwd=repo_root, check=True,
    )
    assert "engine=v2" in result.stdout
    assert (out / "manifest.json").is_file()
    assert (out / "search" / "manifest.json").is_file()
    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["components"]
    assert "coverage" in manifest


def test_cli_default_engine_is_v1(tmp_path):
    # --engine defaults to v1: a plain run produces the old single-file output
    # with no v2 banner, proving the default is unchanged.
    out = tmp_path / "architecture.json"
    repo_root = os.path.dirname(os.path.dirname(__file__))
    result = subprocess.run(
        [sys.executable, "analyze.py", str(POLYGLOT), "-o", str(out)],
        capture_output=True, text=True, cwd=repo_root, check=True,
    )
    assert "engine=v2" not in result.stdout
    assert out.is_file()
    doc = json.loads(out.read_text())
    assert doc["components"] and doc["symbols"]
