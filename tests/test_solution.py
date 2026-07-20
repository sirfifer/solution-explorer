"""Tests for multi-repo solution composition (M1, MULTI-REPO-DESIGN.md).

Every test drives the REAL v2 engine end to end over small synthetic member
repos built in tmp (no mocks): the manifest loader, then ``compose_solution``,
then assertions on the composed projection tree. A new feature has no meaningful
fail-before, so the negative side is covered directly: a bad manifest is rejected
loudly, a missing member path is a loud per-member error with the rest still
composing, a url-only member is parsed-but-unresolved, and a composed member's
projection is byte-identical to a standalone scan of the same repo.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from analyzer.derive import derive_all
from analyzer.extract import extract_activity, extract_repo
from analyzer.project.pipeline import project_split
from analyzer.project.run import default_store_path
from analyzer.solution import compose_solution, load_solution_manifest
from analyzer.solution.manifest import SolutionManifestError
from analyzer.store import FactStore

FIXED_TS = "2020-01-01T00:00:00Z"
FIXED_NOW = datetime(2020, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# synthetic member repos
# ---------------------------------------------------------------------------

def _make_repo(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root


def _server_repo(root: Path) -> Path:
    return _make_repo(
        root,
        {
            "src/app.py": (
                "def main():\n"
                "    return handle('/')\n\n\n"
                "class Server:\n"
                "    def handle(self, path):\n"
                "        return path\n"
            ),
            "README.md": "# Server\n",
        },
    )


def _client_repo(root: Path) -> Path:
    return _make_repo(
        root,
        {
            "src/index.js": (
                "export function greet(name) {\n"
                "  return 'hi ' + name;\n"
                "}\n"
            ),
            "package.json": '{"name": "client"}\n',
        },
    )


def _write_manifest(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def _two_member_manifest(tmp_path: Path) -> Path:
    _server_repo(tmp_path / "server")
    _client_repo(tmp_path / "client")
    return _write_manifest(
        tmp_path / "solution.yml",
        "schema: solution-explorer.solution/v1\n"
        "name: Demo Solution\n"
        "members:\n"
        "  - path: server\n"
        "    label: Backend Server\n"
        "  - path: client\n"
        "    label: Web Client\n"
        "    slug: web\n",
    )


def _compose(manifest_path: Path, out: Path):
    solution = load_solution_manifest(manifest_path)
    return solution, compose_solution(
        solution, out, generated_at=FIXED_TS, now=FIXED_NOW,
        analyzer_version="1.2.0",
    )


# ---------------------------------------------------------------------------
# composition happy path
# ---------------------------------------------------------------------------

def test_compose_emits_member_projections_and_solution_layer(tmp_path):
    manifest_path = _two_member_manifest(tmp_path)
    out = tmp_path / "out"
    _, result = _compose(manifest_path, out)

    # Solution layer files present at the root.
    assert (out / "manifest.json").is_file()
    assert (out / "ai.json").is_file()
    assert (out / "llms.txt").is_file()

    # Each resolved member has a complete standalone split projection.
    for slug in ("server", "web"):
        mdir = out / "members" / slug
        assert (mdir / "manifest.json").is_file()
        assert (mdir / "ai.json").is_file()
        assert (mdir / "llms.txt").is_file()
        assert (mdir / "coverage.json").is_file()
        assert (mdir / "search" / "manifest.json").is_file()
        assert list((mdir / "data").glob("detail-*.json"))

    assert result.solution_name == "Demo Solution"
    assert len(result.composed_members) == 2


def test_solution_manifest_shape(tmp_path):
    manifest_path = _two_member_manifest(tmp_path)
    out = tmp_path / "out"
    _compose(manifest_path, out)

    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["schema"] == "solution-explorer.solution/v1"
    assert manifest["kind"] == "solution-explorer-solution"
    assert manifest["name"] == "Demo Solution"

    # Member order equals manifest order (determinism, decision 4).
    slugs = [m["slug"] for m in manifest["members"]]
    assert slugs == ["server", "web"]

    server = manifest["members"][0]
    assert server["resolved"] is True
    assert server["projection"] == "members/server/"
    assert server["stats"]["total_components"] >= 1
    assert server["coverage"]["source_percent"] == "100"
    assert server["coverage"]["has_gaps"] is False


def test_no_blended_coverage_denominator(tmp_path):
    """Decision 5: coverage is per member, summed transparently, never blended."""
    manifest_path = _two_member_manifest(tmp_path)
    out = tmp_path / "out"
    _compose(manifest_path, out)
    manifest = json.loads((out / "manifest.json").read_text())
    summary = manifest["summary"]

    # A summed, transparent file count exists; there is NO solution-wide percent
    # or blended denominator key anywhere in the summary.
    assert summary["total_source_files"] >= 2
    assert "source_percent" not in summary
    assert not any("percent" in k for k in summary)
    # Each member carries its own percent instead.
    for m in manifest["members"]:
        assert "source_percent" in m["coverage"]


def test_solution_front_door_descends_into_members(tmp_path):
    manifest_path = _two_member_manifest(tmp_path)
    out = tmp_path / "out"
    _compose(manifest_path, out)

    ai = json.loads((out / "ai.json").read_text())
    assert ai["mode"] == "solution"
    assert ai["kind"] == "solution-explorer-solution-front-door"
    member_front_doors = {m["slug"]: m.get("front_door") for m in ai["members"]}
    assert member_front_doors["server"] == "members/server/ai.json"
    assert member_front_doors["web"] == "members/web/ai.json"

    llms = (out / "llms.txt").read_text()
    assert "members/server/ai.json" in llms
    assert "never blended" in llms


# ---------------------------------------------------------------------------
# byte parity with a standalone scan
# ---------------------------------------------------------------------------

def _standalone_split(repo: Path, out: Path):
    """Mirror compose's per-member run exactly, standalone, for byte comparison."""
    store_path = default_store_path(repo)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store = FactStore(str(store_path))
    try:
        extract_repo(repo, store)
        extract_activity(repo, store)
        _, arch = derive_all(store, repo.name, root_path=str(repo))
        project_split(
            arch, out, store=store, root=repo,
            generated_at=FIXED_TS, now=FIXED_NOW, analyzer_version="1.2.0",
        )
    finally:
        store.close()


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def test_member_projection_is_byte_identical_to_standalone(tmp_path):
    """A composed member's projection equals a standalone scan of the repo, byte
    for byte (the solution layer never touches member bytes)."""
    server = _server_repo(tmp_path / "server")
    manifest_path = _write_manifest(
        tmp_path / "solution.yml",
        "schema: solution-explorer.solution/v1\n"
        "name: One\n"
        "members:\n"
        "  - path: server\n"
        "    label: Server\n"
        "    slug: server\n",
    )
    out = tmp_path / "out"
    _compose(manifest_path, out)

    # Standalone run over the SAME repo (warm store now); P4-6 guarantees
    # warm/cold projection parity, so this is a valid byte comparison and the
    # arch name/root_path (repo basename + absolute path) match exactly.
    standalone = tmp_path / "standalone"
    _standalone_split(server, standalone)

    composed_member = _tree_bytes(out / "members" / "server")
    standalone_bytes = _tree_bytes(standalone)
    assert composed_member == standalone_bytes


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------

def test_composition_is_byte_stable(tmp_path):
    manifest_path = _two_member_manifest(tmp_path)
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    _compose(manifest_path, out1)
    _compose(manifest_path, out2)
    assert _tree_bytes(out1) == _tree_bytes(out2)


# ---------------------------------------------------------------------------
# negative: manifest loader
# ---------------------------------------------------------------------------

def test_wrong_schema_is_hard_error(tmp_path):
    mp = _write_manifest(
        tmp_path / "s.yml",
        "schema: something/else\nname: X\nmembers:\n  - path: a\n",
    )
    with pytest.raises(SolutionManifestError, match="schema"):
        load_solution_manifest(mp)


def test_missing_name_is_hard_error(tmp_path):
    mp = _write_manifest(
        tmp_path / "s.yml",
        "schema: solution-explorer.solution/v1\nmembers:\n  - path: a\n",
    )
    with pytest.raises(SolutionManifestError, match="name"):
        load_solution_manifest(mp)


def test_empty_members_is_hard_error(tmp_path):
    mp = _write_manifest(
        tmp_path / "s.yml",
        "schema: solution-explorer.solution/v1\nname: X\nmembers: []\n",
    )
    with pytest.raises(SolutionManifestError, match="members"):
        load_solution_manifest(mp)


def test_not_a_mapping_is_hard_error(tmp_path):
    mp = _write_manifest(tmp_path / "s.yml", "- just\n- a\n- list\n")
    with pytest.raises(SolutionManifestError, match="mapping"):
        load_solution_manifest(mp)


def test_bad_member_rejected_loudly_rest_load(tmp_path, capsys):
    """A member with neither path nor url is rejected loudly; the rest still load."""
    _server_repo(tmp_path / "server")
    mp = _write_manifest(
        tmp_path / "s.yml",
        "schema: solution-explorer.solution/v1\n"
        "name: X\n"
        "members:\n"
        "  - label: Broken\n"        # no path and no url
        "  - path: server\n"
        "    label: Good\n",
    )
    solution = load_solution_manifest(mp)
    assert [m.slug for m in solution.members] == ["server"]
    err = capsys.readouterr().err
    assert "rejecting member[0]" in err


def test_duplicate_slug_rejected_loudly(tmp_path, capsys):
    _server_repo(tmp_path / "a")
    _client_repo(tmp_path / "b")
    mp = _write_manifest(
        tmp_path / "s.yml",
        "schema: solution-explorer.solution/v1\n"
        "name: X\n"
        "members:\n"
        "  - path: a\n"
        "    slug: dup\n"
        "  - path: b\n"
        "    slug: dup\n",
    )
    solution = load_solution_manifest(mp)
    assert len(solution.members) == 1
    assert "duplicate member slug" in capsys.readouterr().err


def test_pyyaml_missing_is_loud(tmp_path, monkeypatch):
    import analyzer.solution.manifest as manifest_mod

    monkeypatch.setattr(manifest_mod, "_yaml", None)
    mp = _write_manifest(tmp_path / "s.yml", "schema: x\nname: y\n")
    with pytest.raises(SolutionManifestError, match="PyYAML"):
        load_solution_manifest(mp)


# ---------------------------------------------------------------------------
# negative: composition
# ---------------------------------------------------------------------------

def test_missing_member_path_is_loud_per_member_error_rest_compose(tmp_path, capsys):
    _server_repo(tmp_path / "server")
    mp = _write_manifest(
        tmp_path / "s.yml",
        "schema: solution-explorer.solution/v1\n"
        "name: X\n"
        "members:\n"
        "  - path: server\n"
        "    label: Good\n"
        "  - path: does-not-exist\n"
        "    label: Gone\n"
        "    slug: gone\n",
    )
    out = tmp_path / "out"
    _, result = _compose(mp, out)

    # The good member composed; the missing one is a loud per-member error.
    assert len(result.composed_members) == 1
    err = capsys.readouterr().err
    assert "does not exist" in err

    manifest = json.loads((out / "manifest.json").read_text())
    gone = next(m for m in manifest["members"] if m["slug"] == "gone")
    assert gone["resolved"] is False
    assert "error" in gone
    good = next(m for m in manifest["members"] if m["slug"] == "server")
    assert good["resolved"] is True


def test_url_member_parsed_but_unresolved(tmp_path, capsys):
    _server_repo(tmp_path / "server")
    mp = _write_manifest(
        tmp_path / "s.yml",
        "schema: solution-explorer.solution/v1\n"
        "name: X\n"
        "members:\n"
        "  - path: server\n"
        "    label: Server\n"
        "  - url: https://github.com/org/remote.git\n"
        "    ref: main\n"
        "    label: Remote Client\n",
    )
    out = tmp_path / "out"
    solution, result = _compose(mp, out)

    remote = next(m for m in solution.members if m.url)
    assert remote.resolved is False
    assert remote.url == "https://github.com/org/remote.git"
    assert remote.ref == "main"

    manifest = json.loads((out / "manifest.json").read_text())
    entry = next(m for m in manifest["members"] if m.get("url"))
    assert entry["resolved"] is False
    assert entry["ref"] == "main"
    assert "unresolved_reason" in entry
    # It is NOT analyzed: no member projection directory for it.
    assert not (out / "members" / entry["slug"]).exists()
    assert "NOT analyzed" in capsys.readouterr().err
