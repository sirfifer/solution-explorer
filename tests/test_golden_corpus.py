"""Tests for scripts/golden-corpus.py (card G2, golden-corpus harness).

The harness fetches a frozen real-world repo at a pinned commit and diffs a
fresh generation against a committed baseline. These tests are hermetic: they
do NOT clone Flask or run the analyzer. Config parsing, corpus discovery, the
exclude-block manager, and the check/diff wiring (including exit codes) are
exercised against synthetic projections. The live fetch+generate path is proven
by the dedicated golden-corpus workflow, plus one opt-in network test guarded by
GOLDEN_CORPUS_NETWORK so the default suite stays fast and offline.

The committed Flask lock is also validated so a malformed pin cannot land.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HARNESS = REPO_ROOT / "scripts" / "golden-corpus.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("golden_corpus", HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gc = _load_module()


@pytest.fixture(autouse=True)
def _restore_module_paths():
    """Snapshot and restore the harness path globals so a CLI test that
    redirects GOLDEN_DIR/CACHE_DIR cannot leak into another test."""
    saved_golden, saved_cache = gc.GOLDEN_DIR, gc.CACHE_DIR
    try:
        yield
    finally:
        gc.GOLDEN_DIR, gc.CACHE_DIR = saved_golden, saved_cache


def _min_projection(**overrides) -> dict:
    proj = {
        "name": "flask",
        "analyzer_version": "1.2.0",
        "components": [{"id": "root", "name": "root", "type": "service"}],
        "relationships": [],
        "findings": [],
        "capabilities": [],
        "data_entities": [],
        "entity_access": [],
        "coverage": {"total": 1, "parsed": 1, "summary": {"parsed": 1}, "inventory": {}},
    }
    proj.update(overrides)
    return proj


def _make_corpus(golden_dir: Path, name: str, *, commit="a" * 40, exclude=None) -> Path:
    d = golden_dir / name
    d.mkdir(parents=True)
    lock = {
        "name": name,
        "repo": f"https://example.com/{name}.git",
        "ref": "1.0.0",
        "commit": commit,
        "exclude": exclude or [],
    }
    (d / "corpus.lock").write_text(json.dumps(lock), encoding="utf-8")
    return d


# ---------------------------------------------------------------------------
# Config parsing and discovery
# ---------------------------------------------------------------------------


def test_load_corpus_valid(tmp_path):
    _make_corpus(tmp_path, "flask")
    corpus = gc.load_corpus("flask", golden_dir=tmp_path)
    assert corpus["name"] == "flask"
    assert corpus["commit"] == "a" * 40
    assert corpus["exclude"] == []


def test_load_corpus_missing_lock(tmp_path):
    with pytest.raises(FileNotFoundError):
        gc.load_corpus("ghost", golden_dir=tmp_path)


def test_load_corpus_missing_required_field(tmp_path):
    d = tmp_path / "broken"
    d.mkdir()
    (d / "corpus.lock").write_text(json.dumps({"name": "broken"}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing 'repo'"):
        gc.load_corpus("broken", golden_dir=tmp_path)


def test_load_corpus_name_mismatch(tmp_path):
    d = tmp_path / "flask"
    d.mkdir()
    (d / "corpus.lock").write_text(
        json.dumps({"name": "notflask", "repo": "x", "commit": "b" * 40}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not match directory"):
        gc.load_corpus("flask", golden_dir=tmp_path)


def test_list_corpora(tmp_path):
    _make_corpus(tmp_path, "flask")
    _make_corpus(tmp_path, "fastapi")
    (tmp_path / "not-a-corpus").mkdir()  # no lock, ignored
    assert gc.list_corpora(golden_dir=tmp_path) == ["fastapi", "flask"]


# ---------------------------------------------------------------------------
# Exclude-block manager
# ---------------------------------------------------------------------------


def test_apply_excludes_is_idempotent(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    gitignore = src / ".gitignore"
    gitignore.write_text("*.pyc\n", encoding="utf-8")
    gc._apply_excludes(src, ["docs/*/", "translated/"])
    once = gitignore.read_text(encoding="utf-8")
    gc._apply_excludes(src, ["docs/*/", "translated/"])
    twice = gitignore.read_text(encoding="utf-8")
    assert once == twice  # no accumulation
    assert once.count("docs/*/") == 1
    assert "*.pyc" in once  # preserved original content


def test_apply_excludes_empty_removes_block(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / ".gitignore").write_text("keep\n", encoding="utf-8")
    gc._apply_excludes(src, ["x/"])
    assert "x/" in (src / ".gitignore").read_text(encoding="utf-8")
    gc._apply_excludes(src, [])
    text = (src / ".gitignore").read_text(encoding="utf-8")
    assert "x/" not in text
    assert "keep" in text


def test_output_dir_is_outside_the_source_tree(tmp_path):
    # Regression: generated projections and their analyzer sidecars (ai.json,
    # sbom.json, ...) must NOT land inside the scanned corpus, or the next scan
    # counts the harness's own output as source and inflates the projection.
    cache = tmp_path / "cache"
    source = cache / "flask"  # where fetch_corpus checks the corpus out
    out = gc._out_dir("flask", cache_dir=cache)
    assert source not in out.parents
    assert out.resolve() != source.resolve()


# ---------------------------------------------------------------------------
# Diff wiring
# ---------------------------------------------------------------------------


def test_diff_against_baseline_clean(tmp_path):
    base = tmp_path / "baseline.json"
    gen = tmp_path / "gen.json"
    proj = _min_projection()
    base.write_text(json.dumps(proj), encoding="utf-8")
    gen.write_text(json.dumps(dict(proj, generated_at="later")), encoding="utf-8")
    diff = gc.diff_against_baseline(gen, base)
    assert diff["has_changes"] is False  # timestamp is not drift


def test_diff_against_baseline_detects_drift(tmp_path):
    base = tmp_path / "baseline.json"
    gen = tmp_path / "gen.json"
    base.write_text(json.dumps(_min_projection()), encoding="utf-8")
    drifted = _min_projection(
        capabilities=[{"id": "cap:new", "kind": "web", "name": "n"}]
    )
    gen.write_text(json.dumps(drifted), encoding="utf-8")
    diff = gc.diff_against_baseline(gen, base)
    assert diff["has_changes"] is True
    assert diff["sections"]["capabilities"]["added"] == ["cap:new"]


# ---------------------------------------------------------------------------
# CLI end to end (hermetic: --generated skips fetch/analyze)
# ---------------------------------------------------------------------------


def _run(module_golden, module_cache, *args):
    """Run the CLI in-process with GOLDEN_DIR/CACHE_DIR redirected."""
    gc.GOLDEN_DIR = module_golden
    gc.CACHE_DIR = module_cache
    return gc.main(list(args))


def test_cli_check_no_drift_exit_zero(tmp_path, capsys):
    golden = tmp_path / "golden"
    cache = tmp_path / "cache"
    d = _make_corpus(golden, "flask")
    (d / "baseline.json").write_text(json.dumps(_min_projection()), encoding="utf-8")
    gen = tmp_path / "gen.json"
    gen.write_text(
        json.dumps(_min_projection(generated_at="x")), encoding="utf-8"
    )
    rc = _run(golden, cache, "check", "flask", "--generated", str(gen))
    assert rc == 0
    assert "no drift" in capsys.readouterr().out.lower()


def test_cli_check_drift_exit_one(tmp_path, capsys):
    golden = tmp_path / "golden"
    cache = tmp_path / "cache"
    d = _make_corpus(golden, "flask")
    (d / "baseline.json").write_text(json.dumps(_min_projection()), encoding="utf-8")
    gen = tmp_path / "gen.json"
    gen.write_text(
        json.dumps(_min_projection(relationships=[{"source": "a", "target": "b", "type": "http"}])),
        encoding="utf-8",
    )
    rc = _run(golden, cache, "check", "flask", "--generated", str(gen))
    assert rc == 1
    assert "GOLDEN DRIFT" in capsys.readouterr().err


def test_cli_check_missing_baseline_exit_two(tmp_path, capsys):
    golden = tmp_path / "golden"
    cache = tmp_path / "cache"
    _make_corpus(golden, "flask")  # lock but no baseline
    gen = tmp_path / "gen.json"
    gen.write_text(json.dumps(_min_projection()), encoding="utf-8")
    rc = _run(golden, cache, "check", "flask", "--generated", str(gen))
    assert rc == 2
    assert "no committed baseline" in capsys.readouterr().err


def test_cli_check_unknown_corpus_exit_two(tmp_path):
    golden = tmp_path / "golden"
    golden.mkdir()
    rc = _run(golden, tmp_path / "cache", "check", "ghost")
    assert rc == 2


def test_cli_list(tmp_path, capsys):
    golden = tmp_path / "golden"
    d = _make_corpus(golden, "flask")
    (d / "baseline.json").write_text(json.dumps(_min_projection()), encoding="utf-8")
    rc = _run(golden, tmp_path / "cache", "list")
    assert rc == 0
    out = capsys.readouterr().out
    assert "flask" in out
    assert "baseline present" in out


# ---------------------------------------------------------------------------
# The committed Flask lock must be well formed (a bad pin cannot land)
# ---------------------------------------------------------------------------


def test_committed_flask_lock_is_valid():
    corpus = gc.load_corpus("flask")  # real tests/golden/flask/corpus.lock
    assert corpus["repo"] == "https://github.com/pallets/flask.git"
    assert corpus["ref"] == "3.1.3"
    # A pin must be a full 40-char SHA, not a mutable tag.
    assert len(corpus["commit"]) == 40
    assert all(c in "0123456789abcdef" for c in corpus["commit"])


def test_committed_flask_baseline_exists_and_matches_identity():
    base = gc.baseline_path("flask")
    assert base.exists(), "the approved Flask baseline must be committed"
    data = json.loads(base.read_text(encoding="utf-8"))
    assert data["name"] == "flask"
    # The baseline is a real full projection with the diffable sections present.
    for section in ("components", "relationships", "findings", "coverage"):
        assert section in data


_FASTAPI_TRANSLATED_DOCS = (
    "de", "es", "fr", "hi", "ja", "ko", "pt", "ru", "tr", "uk", "zh", "zh-hant",
)


def test_committed_fastapi_lock_is_valid():
    corpus = gc.load_corpus("fastapi")  # real tests/golden/fastapi/corpus.lock
    assert corpus["repo"] == "https://github.com/tiangolo/fastapi.git"
    assert corpus["ref"] == "0.139.2"
    # A pin must be a full 40-char SHA, not a mutable tag.
    assert len(corpus["commit"]) == 40
    assert all(c in "0123456789abcdef" for c in corpus["commit"])
    # The FastAPI corpus excludes every translated docs directory (docs/en, the
    # canonical English docs, stays scanned) and docs_src. Dropping an exclude
    # would silently re-include churny translations or version-variant tutorial
    # near-duplicates and move the baseline.
    excludes = set(corpus["exclude"])
    for lang in _FASTAPI_TRANSLATED_DOCS:
        assert f"docs/{lang}/" in excludes
    assert "docs_src/" in excludes
    assert "docs/en/" not in excludes  # English docs must remain scanned


def test_committed_fastapi_baseline_exists_and_matches_identity():
    base = gc.baseline_path("fastapi")
    assert base.exists(), "the approved FastAPI baseline must be committed"
    data = json.loads(base.read_text(encoding="utf-8"))
    assert data["name"] == "fastapi"
    for section in ("components", "relationships", "findings", "coverage"):
        assert section in data
    # The excludes held at generation time: no translated-doc or docs_src file
    # landed in the projection, and English docs did. This is the real proof the
    # exclude mechanism worked, not just that it is configured in the lock.
    paths = [f.get("path", "") for f in data.get("files", []) if isinstance(f, dict)]
    translated = tuple(f"docs/{lang}/" for lang in _FASTAPI_TRANSLATED_DOCS)
    assert not any(p.startswith(translated) for p in paths)
    assert not any(p.startswith("docs_src/") for p in paths)
    assert any(p.startswith("docs/en/") for p in paths)


# ---------------------------------------------------------------------------
# Opt-in live network test (the real fetch + generate + check)
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("GOLDEN_CORPUS_NETWORK") != "1",
    reason="set GOLDEN_CORPUS_NETWORK=1 to run the live fetch+generate+check",
)
@pytest.mark.parametrize("corpus", ["flask", "fastapi"])
def test_live_check_matches_baseline(corpus, tmp_path):
    res = subprocess.run(
        [sys.executable, str(HARNESS), "check", corpus, "--force"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"golden drift or failure:\n{res.stdout}\n{res.stderr}"
